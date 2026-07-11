"""v32.1 — Scheduler: orquestra os watchers, salva WatcherRun/PublicationHit,
gera OpportunityLead pontuado pra cada hit relevante — agora com
deduplicação real (rodar o mesmo fixture duas vezes não cria lead
repetido), acionamento automático de bots opcional (WATCHERS_AUTO_RUN_BOTS),
e status geral honesto (uma fonte falhando vira 'partial', não some)."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from .base import WatcherResult
from .lead_ranker import calcular_score


def _calcular_text_hash(texto: str) -> str:
    return hashlib.sha256((texto or '').strip().lower().encode('utf-8')).hexdigest()


def _calcular_dedupe_key(*, source: str, normalized_cnj: str | None, signal_type: str | None,
                          publication_date: str | None, text_hash: str) -> str:
    """Chave de deduplicação — mesma publicação rodada de novo (mesmo
    fixture, mesmo dia) gera a MESMA chave, então vira atualização de um
    lead existente, não um lead novo."""
    partes = [source or '', normalized_cnj or '', signal_type or '', publication_date or '', text_hash[:16]]
    return '|'.join(partes)


async def rodar_watcher(db, watcher_name: str, publicacoes_fixture: list[dict] | None = None, cnjs_conhecidos: list[str] | None = None) -> dict[str, Any]:
    """Roda UM watcher específico por nome, salva tudo (com deduplicação
    de leads), devolve o resumo.
    watcher_name: 'publication_watcher' | 'datajud_movement_watcher' | 'stj_official_file_watcher'."""
    from ..models import WatcherRun, PublicationHit, OpportunityLead
    from ..config import get_settings

    settings = get_settings()
    auto_run_bots = getattr(settings, 'watchers_auto_run_bots', False)

    run = WatcherRun(watcher_name=watcher_name, status='running')
    db.add(run)
    db.commit()
    db.refresh(run)

    resultado: WatcherResult
    try:
        if watcher_name == 'publication_watcher':
            from .publication_watcher import processar_publicacoes
            resultado = processar_publicacoes(publicacoes_fixture or [])
        elif watcher_name == 'datajud_movement_watcher':
            from .datajud_movement_watcher import varrer_movimentacoes
            resultado = await varrer_movimentacoes(cnjs_conhecidos or [])
        elif watcher_name == 'stj_official_file_watcher':
            from .stj_official_file_watcher import varrer_arquivos_stj
            resultado = await varrer_arquivos_stj(db)
        elif watcher_name == 'tjsp_precatorio_watcher':
            from .tjsp_precatorio_watcher import varrer_precatorios_pendentes_tjsp
            resultado = await varrer_precatorios_pendentes_tjsp()
        else:
            raise ValueError(f'Watcher desconhecido: {watcher_name}')
    except Exception as exc:
        run.status = 'failed'
        run.error = str(exc)
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        return {'watcher_run_id': run.id, 'status': 'failed', 'error': str(exc), 'total_publications': 0, 'total_matches': 0, 'total_leads_created': 0, 'duplicados_ignorados': 0}

    leads_criados = 0
    duplicados_ignorados = 0
    agora = datetime.now(timezone.utc)

    for hit in resultado.hits:
        text_hash = _calcular_text_hash(hit.publication_text)
        publication_hit = PublicationHit(
            watcher_run_id=run.id, source=hit.source, tribunal=hit.tribunal,
            publication_date=hit.publication_date, process_number=hit.process_number,
            normalized_cnj=hit.normalized_cnj, parties_text=hit.parties_text, lawyers_text=hit.lawyers_text,
            publication_text=hit.publication_text, text_hash=text_hash, matched_terms=hit.matched_terms,
            signal_type=hit.signal_type, confidence=hit.confidence, source_url=hit.source_url, raw=hit.raw,
        )
        db.add(publication_hit)

        dedupe_key = _calcular_dedupe_key(
            source=hit.source, normalized_cnj=hit.normalized_cnj, signal_type=hit.signal_type,
            publication_date=hit.publication_date, text_hash=text_hash,
        )

        lead_existente = db.query(OpportunityLead).filter(OpportunityLead.dedupe_key == dedupe_key).first()
        if lead_existente:
            lead_existente.last_seen_at = agora
            lead_existente.seen_count = (lead_existente.seen_count or 1) + 1
            duplicados_ignorados += 1
            db.commit()
            continue

        score_info = calcular_score(
            signal_type=hit.signal_type, cnj=hit.normalized_cnj, tribunal=hit.tribunal,
            ente_devedor=(hit.raw or {}).get('ente_devedor'), natureza_alimentar=bool((hit.raw or {}).get('natureza_alimentar')),
            valor_explicito='valor' in (hit.publication_text or '').lower(),
            segredo_de_justica='segredo de justiça' in (hit.publication_text or '').lower() or 'segredo de justica' in (hit.publication_text or '').lower(),
            termos_negativos=[t for t in (hit.matched_terms or []) if t in {'embargos', 'agravo', 'recurso', 'rescisória', 'rescisoria'}],
        )

        from ..utils.cpf import mask_document, hash_document
        credor_doc = (hit.raw or {}).get('credor_cpf') or (hit.raw or {}).get('credor_cnpj')
        lead = OpportunityLead(
            dedupe_key=dedupe_key, first_seen_at=agora, last_seen_at=agora, seen_count=1,
            source=hit.source, process_number=hit.process_number, normalized_cnj=hit.normalized_cnj,
            tribunal=hit.tribunal, debtor=(hit.raw or {}).get('ente_devedor'),
            creditor_name=(hit.raw or {}).get('credor_nome'),
            creditor_document_masked=mask_document(credor_doc) if credor_doc else None,
            creditor_document_hash=hash_document(credor_doc) if credor_doc else None,
            signal_type=hit.signal_type, estimated_opportunity_type=(hit.raw or {}).get('tipo_acao'),
            confidence_score=score_info['score'], priority=score_info['prioridade'],
            next_action=_montar_proxima_acao(hit, score_info),
            publication_text=hit.publication_text, matched_terms=hit.matched_terms,
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
        leads_criados += 1

        # v32.1: aciona bots automaticamente só se WATCHERS_AUTO_RUN_BOTS=true
        # E a prioridade for alta — nunca por padrão (sobrecarregaria).
        if auto_run_bots and score_info['prioridade'] == 'alta' and lead.normalized_cnj:
            try:
                from ..bots.runner import executar_bots
                from ..models import BotJob, BotStep
                bots_resultado = await executar_bots(lead.normalized_cnj, None, lead.tribunal, 'completo', db=db)
                job = BotJob(
                    input_original=lead.normalized_cnj, tipo_identificado=bots_resultado['tipo_identificado'],
                    objetivo='completo', status=bots_resultado['status'], resumo_humano=bots_resultado['resumo_humano'],
                    proxima_acao=bots_resultado['proxima_acao_recomendada'], raw=bots_resultado,
                )
                db.add(job)
                db.commit()
                db.refresh(job)
                for passo in bots_resultado['bots_executados']:
                    evidence_ids = passo.get('evidence_ids') or []
                    db.add(BotStep(
                        job_id=job.id, bot_name=passo['bot_id'], status=passo['status'],
                        finished_at=datetime.now(timezone.utc) if passo['status'] != 'waiting_user' else None,
                        resultado=passo.get('resultado'), warning='; '.join(passo.get('warnings') or []) or None,
                        next_action=passo.get('next_action'), evidence_id=evidence_ids[0] if evidence_ids else None,
                    ))
                db.commit()
                lead.bot_job_id = job.id
                lead.dossie_url = f'/api/bots/jobs/{job.id}/dossie'
                db.commit()
            except Exception:
                pass  # falha ao acionar bot automático não derruba a rodada do watcher

    run.status = 'completed' if resultado.status != 'failed' else 'failed'
    run.date_from = resultado.date_from
    run.date_to = resultado.date_to
    run.tribunals_scanned = resultado.tribunals_scanned
    run.total_publications = resultado.total_publications
    run.total_matches = len(resultado.hits)
    run.total_leads_created = leads_criados
    run.error = resultado.error
    run.finished_at = datetime.now(timezone.utc)
    db.commit()

    return {
        'watcher_run_id': run.id, 'status': run.status, 'error': run.error,
        'total_publications': run.total_publications, 'total_matches': run.total_matches,
        'total_leads_created': run.total_leads_created, 'duplicados_ignorados': duplicados_ignorados,
    }


def _montar_proxima_acao(hit, score_info) -> str:
    ente_devedor = (hit.raw or {}).get('ente_devedor')
    tipo_acao = (hit.raw or {}).get('tipo_acao')
    contexto = ''
    if ente_devedor:
        contexto = f' Ação contra {ente_devedor}' + (f' ({tipo_acao})' if tipo_acao else '') + '.'

    if hit.signal_type in {'precatorio_confirmado', 'rpv_confirmada', 'oficio_requisitorio'}:
        return f'Sinal forte de {hit.signal_type.replace("_", " ")} — rodar bots pra confirmar detalhes e gerar dossiê.' + contexto
    if hit.signal_type in {'pre_rpv', 'pre_precatorio', 'calculo_homologado', 'transito_em_julgado', 'cumprimento_sentenca'}:
        return f'Sinal de pré-oportunidade ({hit.signal_type.replace("_", " ")}) — acompanhar evolução, ainda não é precatório/RPV confirmado.' + contexto
    if hit.signal_type in {'credito_judicial_potencial', 'sentenca_favoravel', 'acordao_favoravel', 'sentenca_proferida'}:
        return (
            f'Possível crédito judicial contra ente público{contexto} '
            f'Ainda precisamos verificar fase processual, sentença, cálculos, trânsito em julgado e eventual RPV/precatório.'
        )
    return 'Sinal fraco — revisar manualmente antes de investir tempo.'


async def rodar_todos_os_watchers(db, publicacoes_fixture: list[dict] | None = None, cnjs_conhecidos: list[str] | None = None) -> dict[str, Any]:
    """Roda os 3 watchers em sequência — uma falhar não impede as outras.
    Devolve overall_status honesto: se qualquer watcher falhar, o geral
    vira 'partial' (não 'completed' escondendo o problema)."""
    resultados = {}
    for nome in ['publication_watcher', 'datajud_movement_watcher', 'stj_official_file_watcher']:
        try:
            resultados[nome] = await rodar_watcher(db, nome, publicacoes_fixture=publicacoes_fixture, cnjs_conhecidos=cnjs_conhecidos)
        except Exception as exc:
            resultados[nome] = {'status': 'failed', 'error': str(exc)}

    status_individuais = [r.get('status') for r in resultados.values()]
    if all(s == 'completed' for s in status_individuais):
        overall_status = 'completed'
    elif all(s == 'failed' for s in status_individuais):
        overall_status = 'failed'
    else:
        overall_status = 'partial'

    return {'overall_status': overall_status, 'watchers': resultados}
