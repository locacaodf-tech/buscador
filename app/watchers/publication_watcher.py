"""v32 — Publication Watcher: varre publicações em busca de sinais de
crédito judicial. Escaneia uma LISTA de publicações (texto + metadados)
já fornecida — não decide sozinho de onde essas publicações vêm.

Honestidade importante (pesquisada antes de construir, não presumida):
o DJEN (Diário de Justiça Eletrônico Nacional, https://comunica.pje.jus.br/)
tem uma API de consulta documentada (Domicílio Judicial Eletrônico,
docs.pdpj.jus.br), mas ela exige cabeçalho `tenantId` vinculado a uma conta
institucional/advocatícia — não é uma busca pública aberta por
palavra-chave sem essa credencial. Não encontrei, nas buscas feitas, uma
forma de consultar publicações nacionalmente sem esse vínculo.

Por isso, nesta entrega, o Publication Watcher funciona com:
1. Fixtures locais (para provar a esteira completa: publicação → sinal →
   lead → bots → dossiê).
2. Uma função de integração pronta para receber publicações reais de
   QUALQUER fonte que você já tenha acesso (ex.: se você ou sua esposa
   tiverem uma conta de advogado(a) com acesso ao Domicílio Judicial
   Eletrônico, dá para plugar isso aqui sem mudar mais nada)."""
from __future__ import annotations

from typing import Any

from .base import HitEncontrado, WatcherResult
from .precatorio_signal_engine import classificar_publicacao
from ..utils.cnj import normalize_cnj, format_cnj, infer_tribunal_from_cnj


def processar_publicacoes(publicacoes: list[dict[str, Any]], source: str = 'fixture_local') -> WatcherResult:
    """Recebe uma lista de publicações já obtidas (cada uma com pelo menos
    'texto', e opcionalmente 'tribunal', 'data', 'numero_processo',
    'partes', 'advogados', 'url') e classifica cada uma, gerando os
    HitEncontrado que batem com algum sinal de interesse.

    Não busca nada sozinho — quem chama essa função é responsável por
    fornecer as publicações (fixture local, ou uma fonte real que você
    tenha acesso)."""
    hits: list[HitEncontrado] = []
    tribunais_vistos = set()

    for pub in publicacoes:
        texto = pub.get('texto', '')
        if not texto:
            continue
        classificacao = classificar_publicacao(texto)

        cnj_normalizado = None
        tribunal = pub.get('tribunal')
        numero = pub.get('numero_processo')
        if numero:
            n = normalize_cnj(numero)
            if len(n) == 20:
                cnj_normalizado = format_cnj(n)
                tribunal = tribunal or infer_tribunal_from_cnj(n)
        else:
            # v33: achado real — texto colado (não estruturado) nunca
            # tinha numero_processo separado, então o CNJ nunca era
            # extraído mesmo estando claramente escrito no texto. Reusa
            # o mesmo extrator do IntakeBot, já testado.
            from ..services.whatsapp_intake import extrair_cnj_candidatos
            candidatos = extrair_cnj_candidatos(texto)
            if candidatos:
                n = candidatos[0]['cnj']
                cnj_normalizado = format_cnj(n)
                numero = cnj_normalizado
                tribunal = tribunal or infer_tribunal_from_cnj(n)

        if tribunal:
            tribunais_vistos.add(tribunal)

        if classificacao['signal_type'] in {'descartar'}:
            continue  # publicação genérica demais, nem vira hit

        from ..services.whatsapp_intake import extrair_tipo_acao
        tipo_acao = extrair_tipo_acao(texto)

        hits.append(HitEncontrado(
            source=source, tribunal=tribunal, publication_date=pub.get('data'),
            process_number=numero, normalized_cnj=cnj_normalizado,
            parties_text=pub.get('partes'), lawyers_text=pub.get('advogados'),
            publication_text=texto, matched_terms=classificacao['termos_batidos'],
            signal_type=classificacao['signal_type'], confidence='medium' if cnj_normalizado else 'low',
            source_url=pub.get('url'),
            raw={'ente_devedor': classificacao['ente_devedor'], 'natureza_alimentar': classificacao['natureza_alimentar'], 'tipo_acao': tipo_acao},
        ))

    return WatcherResult(
        watcher_name='publication_watcher', status='completed',
        tribunals_scanned=sorted(tribunais_vistos), total_publications=len(publicacoes), hits=hits,
    )
