"""v32 — DataJud Movement Watcher: para processos que a gente já
conhece/salvou (de diligências anteriores), consulta de novo o DataJud e
compara com o que já tínhamos — se apareceu movimentação nova
compatível com algum sinal de interesse, vira um hit. Reaproveita o
DataJudConnector já existente, não duplica nada."""
from __future__ import annotations

from typing import Any

from .base import HitEncontrado, WatcherResult
from .precatorio_signal_engine import classificar_publicacao
from ..connectors.datajud import DataJudConnector
from ..utils.cnj import format_cnj, infer_tribunal_from_cnj


async def varrer_movimentacoes(cnjs_conhecidos: list[str]) -> WatcherResult:
    """Recebe uma lista de CNJs já conhecidos (ex.: de diligências
    anteriores salvas no DiligenciaLog/BotJob) e consulta o DataJud de
    novo pra cada um, olhando se alguma movimentação recente bate com
    algum sinal de interesse (precatório expedido, RPV, trânsito em
    julgado etc.)."""
    connector = DataJudConnector()
    hits: list[HitEncontrado] = []
    tribunais_vistos = set()
    falhas = 0

    for cnj in cnjs_conhecidos:
        tribunal = infer_tribunal_from_cnj(cnj)
        if tribunal:
            tribunais_vistos.add(tribunal)
        try:
            items = await connector.search('cnj', cnj, tribunals=[tribunal] if tribunal else None, max_results=5)
        except Exception:
            falhas += 1
            continue

        for item in items:
            if item.get('error'):
                continue
            source = item.get('source') or {}
            movimentos = source.get('movimentos') or []
            texto_movimentos = ' '.join(str(m.get('nome') or m.get('descricao') or '') for m in movimentos if isinstance(m, dict))
            if not texto_movimentos:
                continue
            classificacao = classificar_publicacao(texto_movimentos)
            if classificacao['signal_type'] in {None, 'descartar'}:
                continue
            hits.append(HitEncontrado(
                source='datajud_movement_watcher', tribunal=tribunal, publication_date=None,
                process_number=cnj, normalized_cnj=format_cnj(cnj),
                parties_text=None, lawyers_text=None, publication_text=texto_movimentos,
                matched_terms=classificacao['termos_batidos'], signal_type=classificacao['signal_type'],
                confidence='high', raw={'ente_devedor': classificacao['ente_devedor']},
            ))

    status = 'completed' if falhas == 0 else ('partial' if hits or falhas < len(cnjs_conhecidos) else 'failed')
    return WatcherResult(
        watcher_name='datajud_movement_watcher', status=status,
        tribunals_scanned=sorted(tribunais_vistos), total_publications=len(cnjs_conhecidos), hits=hits,
        error=f'{falhas} consulta(s) falharam.' if falhas else None,
    )
