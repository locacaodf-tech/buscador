"""v32 — Scheduler: orquestra os watchers, salva WatcherRun/PublicationHit,
gera OpportunityLead pontuado pra cada hit relevante. Uma fonte falhando
não derruba as demais (mesmo princípio dos bots)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .base import WatcherResult
from .lead_ranker import calcular_score


async def rodar_watcher(db, watcher_name: str, publicacoes_fixture: list[dict] | None = None, cnjs_conhecidos: list[str] | None = None) -> dict[str, Any]:
    """Roda UM watcher específico por nome, salva tudo, devolve o resumo.
    watcher_name: 'publication_watcher' | 'datajud_movement_watcher' | 'stj_official_file_watcher'."""
    from ..models import WatcherRun, PublicationHit, OpportunityLead

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
        else:
            raise ValueError(f'Watcher desconhecido: {watcher_name}')
    except Exception as exc:
        run.status = 'failed'
        run.error = str(exc)
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        return {'watcher_run_id': run.id, 'status': 'failed', 'error': str(exc), 'total_publications': 0, 'total_matches': 0, 'total_leads_created': 0}

    leads_criados = 0
    for hit in resultado.hits:
        publication_hit = PublicationHit(
            watcher_run_id=run.id, source=hit.source, tribunal=hit.tribunal,
            publication_date=hit.publication_date, process_number=hit.process_number,
            normalized_cnj=hit.normalized_cnj, parties_text=hit.parties_text, lawyers_text=hit.lawyers_text,
            publication_text=hit.publication_text, matched_terms=hit.matched_terms,
            signal_type=hit.signal_type, confidence=hit.confidence, source_url=hit.source_url, raw=hit.raw,
        )
        db.add(publication_hit)

        score_info = calcular_score(
            signal_type=hit.signal_type, cnj=hit.normalized_cnj, tribunal=hit.tribunal,
            ente_devedor=(hit.raw or {}).get('ente_devedor'), natureza_alimentar=bool((hit.raw or {}).get('natureza_alimentar')),
            valor_explicito='valor' in (hit.publication_text or '').lower(),
            segredo_de_justica='segredo de justiça' in (hit.publication_text or '').lower() or 'segredo de justica' in (hit.publication_text or '').lower(),
            termos_negativos=[t for t in (hit.matched_terms or []) if t in {'embargos', 'agravo', 'recurso', 'rescisória', 'rescisoria'}],
        )

        lead = OpportunityLead(
            source=hit.source, process_number=hit.process_number, normalized_cnj=hit.normalized_cnj,
            tribunal=hit.tribunal, debtor=(hit.raw or {}).get('ente_devedor'),
            signal_type=hit.signal_type, confidence_score=score_info['score'], priority=score_info['prioridade'],
            next_action=_montar_proxima_acao(hit, score_info),
        )
        db.add(lead)
        leads_criados += 1

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
        'total_leads_created': run.total_leads_created,
    }


def _montar_proxima_acao(hit, score_info) -> str:
    if hit.signal_type in {'precatorio_confirmado', 'rpv_confirmada', 'oficio_requisitorio'}:
        return f'Sinal forte de {hit.signal_type.replace("_", " ")} — rodar bots pra confirmar detalhes e gerar dossiê.'
    if hit.signal_type in {'pre_rpv', 'pre_precatorio', 'calculo_homologado', 'transito_em_julgado', 'cumprimento_sentenca'}:
        return f'Sinal de pré-oportunidade ({hit.signal_type.replace("_", " ")}) — acompanhar evolução, ainda não é precatório/RPV confirmado.'
    return 'Sinal fraco — revisar manualmente antes de investir tempo.'


async def rodar_todos_os_watchers(db, publicacoes_fixture: list[dict] | None = None, cnjs_conhecidos: list[str] | None = None) -> dict[str, Any]:
    """Roda os 3 watchers em sequência — uma falhar não impede as outras."""
    resultados = {}
    for nome in ['publication_watcher', 'datajud_movement_watcher', 'stj_official_file_watcher']:
        try:
            resultados[nome] = await rodar_watcher(db, nome, publicacoes_fixture=publicacoes_fixture, cnjs_conhecidos=cnjs_conhecidos)
        except Exception as exc:
            resultados[nome] = {'status': 'failed', 'error': str(exc)}
    return resultados
