"""v31d — Auditoria multi-tribunal DataJud: mostra exatamente qual alias e
endpoint foram consultados pra um CNJ, não só "não encontramos". Reaproveita
o DataJudConnector e o TRIBUNAL_ALIASES já existentes — não cria conector
novo, só expõe o que já acontece internamente de forma transparente."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from ..connectors.datajud import DataJudConnector
from ..connectors.tribunal_registry import TRIBUNAL_ALIASES
from ..utils.cnj import normalize_cnj, format_cnj, infer_tribunal_from_cnj

# Fontes manuais oficiais por tribunal — só as que foram verificadas de
# fato (busca real, não palpite). Pra qualquer tribunal fora desta lista,
# o diagnóstico monta a URL pelo padrão oficial (www.<sigla>.jus.br) e
# marca como "padrão, não verificado individualmente" — nunca finge
# certeza sobre um link que não conferi.
FONTES_MANUAIS_VERIFICADAS = {
    'TRF1': 'https://processual.trf1.jus.br/consultaProcessual/numeroProcesso.php?secao=TRF1',
    'TJPE': 'https://certidoesunificadas.app.tjpe.jus.br/',
}


def _endpoint_e_alias(tribunal: str) -> tuple[str | None, str | None]:
    """Devolve (alias, endpoint) sem lançar exceção — usado só pro
    diagnóstico, que precisa continuar mesmo se o alias não existir."""
    connector = DataJudConnector()
    try:
        endpoint = connector.endpoint_for(tribunal)
        alias = TRIBUNAL_ALIASES.get(tribunal.strip().upper())
        return alias, endpoint
    except Exception:
        return None, None


def _fonte_manual_para(tribunal: str | None) -> str:
    if not tribunal:
        return 'Tribunal não identificado — não há fonte manual específica a sugerir.'
    if tribunal in FONTES_MANUAIS_VERIFICADAS:
        return FONTES_MANUAIS_VERIFICADAS[tribunal]
    # Padrão oficial da Justiça brasileira (jus.br) — não verificado
    # individualmente pra este tribunal específico, mas é o padrão de
    # domínio usado por praticamente todo tribunal brasileiro.
    return f'https://www.{tribunal.lower()}.jus.br/ (padrão jus.br — não verificado individualmente pra este tribunal)'


async def diagnosticar_cnj(cnj_original: str, tribunal_hint: str | None = None) -> dict[str, Any]:
    """Ponto único de diagnóstico: normaliza, infere segmento/tribunal,
    resolve alias/endpoint, tenta a consulta real no DataJud pra ESSE
    tribunal especificamente, e devolve tudo — nunca só 'não encontrado'."""
    agora = datetime.now(timezone.utc).isoformat()
    normalizado = normalize_cnj(cnj_original)

    if len(normalizado) != 20:
        return {
            'cnj_original': cnj_original, 'cnj_normalizado': None, 'segmento': None,
            'tribunal_inferido': None, 'alias_datajud': None, 'endpoint': None,
            'status_http': None, 'resultado': 'cnj_invalido', 'erro': None,
            'proxima_acao': 'CNJ inválido — precisa ter 20 dígitos no formato NNNNNNN-DD.AAAA.J.TR.OOOO.',
            'consultado_em': agora,
        }

    from ..services.whatsapp_intake import SEGMENTO_INFO
    segmento_codigo = normalizado[13]
    segmento_nome = SEGMENTO_INFO.get(segmento_codigo, {}).get('nome', f'Segmento {segmento_codigo} (não catalogado)')
    tribunal = (tribunal_hint or '').upper() or infer_tribunal_from_cnj(normalizado)

    base = {
        'cnj_original': cnj_original, 'cnj_normalizado': format_cnj(normalizado),
        'segmento': segmento_nome, 'tribunal_inferido': tribunal, 'consultado_em': agora,
    }

    if not tribunal:
        base.update({
            'alias_datajud': None, 'endpoint': None, 'status_http': None,
            'resultado': 'tribunal_nao_inferido', 'erro': None,
            'proxima_acao': f'Não foi possível inferir o tribunal específico pra este CNJ ({segmento_nome}). Consulte a fonte oficial correspondente a esse segmento.',
        })
        return base

    alias, endpoint = _endpoint_e_alias(tribunal)
    fonte_manual = _fonte_manual_para(tribunal)

    if not alias or not endpoint:
        base.update({
            'alias_datajud': None, 'endpoint': None, 'status_http': None,
            'resultado': 'alias_nao_configurado', 'erro': None,
            'proxima_acao': f'Tribunal inferido ({tribunal}), mas alias DataJud não configurado no registry local. Fonte manual: {fonte_manual}',
        })
        return base

    base.update({'alias_datajud': alias, 'endpoint': endpoint})

    connector = DataJudConnector()
    payload = {'size': 10, 'query': {'match': {'numeroProcesso': normalizado}}}
    try:
        import httpx
        async with httpx.AsyncClient(timeout=connector.settings.datajud_timeout_seconds) as client:
            response = await client.post(endpoint, headers=connector.headers, json=payload)
        base['status_http'] = response.status_code
        if response.status_code >= 400:
            base.update({
                'resultado': 'erro', 'erro': f'HTTP {response.status_code}: {response.text[:300]}',
                'proxima_acao': f'Não foi possível consultar o DataJud para {tribunal} (alias {alias}) agora. Fonte manual: {fonte_manual}',
            })
            return base
        data = response.json()
        hits = ((data or {}).get('hits') or {}).get('hits') or []
        if hits:
            base.update({
                'resultado': 'encontrado', 'erro': None,
                'proxima_acao': f'Processo encontrado no DataJud para {tribunal} (alias {alias}).',
                'total_encontrado': len(hits),
            })
        else:
            base.update({
                'resultado': 'vazio', 'erro': None,
                'proxima_acao': (
                    f'Consultamos o DataJud no tribunal {tribunal} e não houve retorno para esse CNJ. '
                    f'O processo pode não estar indexado, pode estar restrito ou o número pode estar '
                    f'incorreto. Próxima ação: consultar o portal oficial do tribunal ({fonte_manual}).'
                ),
            })
        return base
    except Exception as exc:
        base.update({
            'status_http': None, 'resultado': 'erro', 'erro': str(exc),
            'proxima_acao': f'Não foi possível consultar o DataJud para {tribunal} (alias {alias}) agora — {exc}. Fonte manual: {fonte_manual}',
        })
        return base
