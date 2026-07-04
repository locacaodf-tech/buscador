"""Motor Operacional de Diligência (v28) — camada única de backend que
recebe qualquer dado digitado e decide, sozinha, quais serviços já
existentes consultar, devolvendo uma resposta humana e estruturada.

Isso NÃO duplica lógica: cada ramo abaixo chama um serviço que já existe e
já é testado (DataJud, STJ XLSX, planejador de precatório, certidões). Este
arquivo só orquestra e traduz pra linguagem humana — a mesma decisão que
antes vivia espalhada no JavaScript da tela agora vive aqui, testável e
reaproveitável por qualquer cliente (tela, script, outra IA).

Escopo deliberadamente enxuto (pedido explícito do usuário): sem fila de
jobs, sem tabelas novas, sem "bots" — cada chamada roda e responde na hora.
"""
from __future__ import annotations

from typing import Any

from .identifier import infer_identifier
from .official_precatorio_sources import build_precatorio_route_plan
from .certificate_center import build_certificate_plan
from . import stj_uploads
from ..connectors.datajud import DataJudConnector
from ..connectors.base import ConnectorError, ProviderNotConfigured, SearchNotSupported
from ..config import get_settings
from ..utils.cpf import only_digits


def _etapa(nome: str, status: str, detalhe: str = '') -> dict[str, str]:
    """Uma 'etapa executada' — a versão enxuta do que os documentos
    chamavam de bot: só um registro de o que foi tentado e o resultado."""
    return {'nome': nome, 'status': status, 'detalhe': detalhe}


def _judit_configurada() -> bool:
    settings = get_settings()
    return bool(settings.judit_enabled and settings.judit_api_key)


async def _consultar_cnj(valor: str, tribunal_hint: str | None) -> dict[str, Any]:
    etapas = []
    resultados_confirmados = []
    indicios = []
    pendencias = []
    proxima_acao = None
    raw = {}

    connector = DataJudConnector()
    tribunals = [tribunal_hint.upper()] if tribunal_hint else None
    try:
        items = await connector.search('cnj', valor, tribunals=tribunals, max_results=10)
    except (ConnectorError, SearchNotSupported, ProviderNotConfigured) as exc:
        etapas.append(_etapa('DataJud', 'falhou', str(exc)))
        pendencias.append('DataJud não respondeu — tente novamente em instantes ou confira o número.')
        proxima_acao = 'DataJud não respondeu agora. Confira o número CNJ e tente de novo em alguns instantes.'
        raw['datajud_erro'] = str(exc)
        return {
            'etapas': etapas, 'resultados_confirmados': resultados_confirmados,
            'indicios': indicios, 'pendencias': pendencias,
            'proxima_acao': proxima_acao, 'raw': raw,
        }

    raw['datajud_items'] = items
    erros = [i for i in items if i.get('error')]
    encontrados = [i for i in items if not i.get('error')]

    if erros and not encontrados:
        etapas.append(_etapa('DataJud', 'falhou', '; '.join(str(e.get('error')) for e in erros[:3])))
        pendencias.append('DataJud não respondeu pra este número agora.')
        proxima_acao = 'DataJud não respondeu agora. Tente de novo em instantes.'
        return {
            'etapas': etapas, 'resultados_confirmados': resultados_confirmados,
            'indicios': indicios, 'pendencias': pendencias,
            'proxima_acao': proxima_acao, 'raw': raw,
        }

    if not encontrados:
        etapas.append(_etapa('DataJud', 'concluido', 'Nenhum processo encontrado para este CNJ.'))
        proxima_acao = 'Não encontramos esse processo no DataJud. Confira o número, ou tente o portal do tribunal diretamente.'
        return {
            'etapas': etapas, 'resultados_confirmados': resultados_confirmados,
            'indicios': indicios, 'pendencias': pendencias,
            'proxima_acao': proxima_acao, 'raw': raw,
        }

    r = encontrados[0]
    etapas.append(_etapa('DataJud', 'concluido', f"Tribunal consultado: {r.get('tribunal', '?')}"))
    tem_indicio = (r.get('precatorio_score') or 0) >= 40
    resultado = {
        'fonte': 'DataJud/CNJ',
        'numero_cnj': r.get('numero_processo') or valor,
        'tribunal': r.get('tribunal'),
        'classe': r.get('classe'),
        'assunto': r.get('assunto'),
        'orgao_julgador': r.get('orgao_julgador'),
        'ultima_movimentacao': r.get('ultima_atualizacao'),
    }
    if tem_indicio:
        indicios.append({
            'tipo': 'precatorio_rpv',
            'descricao': 'Indício de precatório/RPV encontrado no processo.',
            'confirmacao_oficial_pendente': True,
            'fonte_provavel': r.get('tribunal'),
        })
        proxima_acao = 'Há apenas indício processual. Para confirmar precatório, consulte a fonte oficial do tribunal ou use "Localizar precatório/RPV".'
    else:
        resultados_confirmados.append(resultado)
        proxima_acao = 'Processo encontrado, sem indício de precatório por enquanto.'

    return {
        'etapas': etapas, 'resultados_confirmados': [resultado] if not tem_indicio else [],
        'indicios': indicios, 'pendencias': pendencias,
        'proxima_acao': proxima_acao, 'raw': raw,
    }


def _consultar_stj(tipo: str, valor: str) -> dict[str, Any]:
    etapas = []
    resultados_confirmados = []
    pendencias = []
    fontes_manuais = []

    stj_tipo = 'name' if tipo == 'name' else ('sequencial' if tipo in {'unknown', 'sequencial'} else tipo)
    data = stj_uploads.search_uploaded_files(stj_tipo, valor)

    if data['status'] == 'not_loaded':
        etapas.append(_etapa('STJ XLSX', 'pendente', 'Arquivo oficial do STJ ainda não carregado.'))
        pendencias.append('Carregar o XLSX oficial do STJ antes de buscar.')
        fontes_manuais.append({'fonte': 'STJ - upload manual do XLSX oficial', 'acao': 'Ir para upload STJ'})
        proxima_acao = 'Carregue o XLSX oficial do STJ na tela do STJ, depois busque de novo.'
        return {
            'etapas': etapas, 'resultados_confirmados': resultados_confirmados,
            'pendencias': pendencias, 'fontes_manuais': fontes_manuais,
            'proxima_acao': proxima_acao, 'raw': data,
        }

    if not data['results']:
        etapas.append(_etapa('STJ XLSX', 'concluido', 'Nenhum registro encontrado nos arquivos carregados.'))
        proxima_acao = 'Não encontramos esse dado nos arquivos do STJ já carregados. Confira o valor ou tente outro dado (CNJ, nome).'
        return {
            'etapas': etapas, 'resultados_confirmados': resultados_confirmados,
            'pendencias': pendencias, 'fontes_manuais': fontes_manuais,
            'proxima_acao': proxima_acao, 'raw': data,
        }

    etapas.append(_etapa('STJ XLSX', 'concluido', f"{len(data['results'])} registro(s) encontrado(s)."))
    for r in data['results']:
        resultados_confirmados.append({
            'fonte': r.get('fonte'),
            'sequencial': r.get('sequencial'),
            'processo': r.get('numero_processo'),
            'credor': r.get('credor_nome'),
            'valor': r.get('valor'),
            'previsao_pagamento': r.get('previsao_pagamento'),
            'arquivo': r.get('arquivo_original'),
            'aba': r.get('aba'),
            'linha': r.get('linha_arquivo'),
            'uploaded_at': r.get('uploaded_at'),
        })
    proxima_acao = 'Dado encontrado nos arquivos oficiais do STJ que você já carregou.'
    return {
        'etapas': etapas, 'resultados_confirmados': resultados_confirmados,
        'pendencias': pendencias, 'fontes_manuais': fontes_manuais,
        'proxima_acao': proxima_acao, 'raw': data,
    }


def _consultar_pessoa(tipo: str, valor: str) -> dict[str, Any]:
    """CPF/CNPJ/OAB: sem provider comercial configurado, nunca finge que
    pesquisou — explica a dependência real e segue com o que for possível."""
    etapas = []
    pendencias = []
    fontes_manuais = []
    rotulo = {'cpf': 'CPF', 'cnpj': 'CNPJ', 'oab': 'OAB'}.get(tipo, tipo.upper())

    if _judit_configurada():
        etapas.append(_etapa('Provider comercial (Judit)', 'concluido', 'Configurada — busca nacional disponível via /api/search.'))
        proxima_acao = f'Judit está configurada. Use a busca avançada (provider=judit) pra consultar {rotulo} nacionalmente.'
        return {'etapas': etapas, 'pendencias': pendencias, 'fontes_manuais': fontes_manuais, 'proxima_acao': proxima_acao}

    etapas.append(_etapa('Provider comercial', 'nao_configurado', 'Nenhum provider comercial configurado.'))
    pendencias.append(f'Busca nacional por {rotulo} depende de provider comercial ou base própria ainda não configurada.')
    fontes_manuais.append({'fonte': 'Consulta manual em provedor externo (opcional)', 'acao': 'Registrar resultado manual depois de consultar por fora'})
    proxima_acao = (
        f'{rotulo} identificado corretamente. A busca nacional automática por pessoa depende de provider comercial '
        'ou base própria ainda não configurada. A diligência continua com as fontes disponíveis: STJ XLSX (por nome), '
        'DataJud (quando houver CNJ), planejamento de certidões, fontes oficiais e evidência manual.'
    )
    return {'etapas': etapas, 'pendencias': pendencias, 'fontes_manuais': fontes_manuais, 'proxima_acao': proxima_acao}


def _consultar_precatorio(tipo: str, valor: str, uf: str | None, tribunal: str | None) -> dict[str, Any]:
    etapas = []
    extra_params: dict[str, Any] = {}
    if uf:
        extra_params['uf'] = uf
    if tribunal:
        extra_params['tribunal'] = tribunal

    plano = build_precatorio_route_plan(tipo, valor, extra_params)
    faltando = plano.get('missing_recommended_fields') or []
    candidatos = plano.get('candidate_sources') or []
    etapas.append(_etapa('Plano de precatório/RPV', 'concluido', f'{len(candidatos)} fonte(s) candidata(s) mapeada(s).'))

    pendencias = [f'Informe {campo} para restringir melhor o plano.' for campo in faltando]
    prontas = [c for c in candidatos if c.get('integration_status') in {'implemented', 'implemented_partial', 'implemented_configurable'}]
    if prontas:
        proxima_acao = f'Comece pela fonte "{prontas[0].get("name")}", que já responde automaticamente.'
    elif faltando:
        proxima_acao = f'Informe {faltando[0]} pra destravar mais fontes no plano.'
    else:
        proxima_acao = 'Confira as fontes oficiais sugeridas no plano — nenhuma automatizada ainda pra este caso.'

    return {'etapas': etapas, 'pendencias': pendencias, 'proxima_acao': proxima_acao, 'raw': plano}


def _planejar_certidao(valor: str) -> dict[str, Any]:
    etapas = []
    plano = build_certificate_plan(valor, None)
    etapas.append(_etapa('Planejamento de certidões', 'concluido', f"{len(plano.get('steps', []))} fonte(s) no plano."))
    proxima_acao = 'Veja o plano de certidões — nunca confirma "nada consta" sem certidão real emitida.'
    return {'etapas': etapas, 'proxima_acao': proxima_acao, 'raw': plano}


async def run_diligencia(
    input_texto: str,
    uf: str | None = None,
    tribunal: str | None = None,
    objetivo: str = 'completo',
) -> dict[str, Any]:
    """Ponto único de entrada do motor. Recebe o que o usuário digitou e
    devolve uma resposta humana e estruturada, reaproveitando os serviços
    que já existem — nunca inventa dado, nunca finge que pesquisou."""
    resolved = infer_identifier(input_texto)
    tipo = resolved.search_type
    valor = resolved.search_key

    etapas: list[dict[str, str]] = [_etapa('Identificação', 'concluido', f'Tipo identificado: {tipo} (confiança: {resolved.confidence}).')]
    resultados_confirmados: list[dict[str, Any]] = []
    indicios: list[dict[str, Any]] = []
    pendencias: list[str] = list(resolved.notes)
    fontes_manuais: list[dict[str, str]] = []
    proxima_acao = None
    raw_avancado: dict[str, Any] = {'tipo_bruto': tipo, 'entrada_original': input_texto}

    if objetivo == 'certidao':
        parte = _planejar_certidao(valor)
        etapas += parte['etapas']
        proxima_acao = parte['proxima_acao']
        raw_avancado['certidoes'] = parte['raw']

    elif tipo in {'cnj', 'numero_processo'}:
        parte = await _consultar_cnj(valor, tribunal)
        etapas += parte['etapas']
        resultados_confirmados += parte['resultados_confirmados']
        indicios += parte['indicios']
        pendencias += parte['pendencias']
        proxima_acao = parte['proxima_acao']
        raw_avancado['datajud'] = parte['raw']

    elif tipo == 'name':
        parte = _consultar_stj('name', valor)
        etapas += parte['etapas']
        resultados_confirmados += parte['resultados_confirmados']
        pendencias += parte['pendencias']
        fontes_manuais += parte['fontes_manuais']
        proxima_acao = parte['proxima_acao']
        raw_avancado['stj'] = parte['raw']
        if not resultados_confirmados and _judit_configurada() is False:
            pendencias.append('Busca nacional por nome (fora do STJ) depende de provider comercial ainda não configurado.')

    elif tipo in {'cpf', 'cnpj', 'oab'}:
        parte = _consultar_pessoa(tipo, valor)
        etapas += parte['etapas']
        pendencias += parte['pendencias']
        fontes_manuais += parte['fontes_manuais']
        proxima_acao = parte['proxima_acao']

    elif tipo == 'unknown':
        digits = only_digits(valor)
        if digits and 3 <= len(digits) <= 8:
            # Pode ser sequencial do STJ — tenta primeiro, é reversível e barato.
            parte = _consultar_stj('sequencial', digits)
            etapas += parte['etapas']
            resultados_confirmados += parte['resultados_confirmados']
            pendencias += parte['pendencias']
            fontes_manuais += parte['fontes_manuais']
            proxima_acao = parte['proxima_acao']
            raw_avancado['stj'] = parte['raw']
        else:
            parte = _consultar_precatorio('precatorio_number', valor, uf, tribunal)
            etapas += parte['etapas']
            pendencias += parte['pendencias']
            proxima_acao = parte['proxima_acao']
            raw_avancado['plano_precatorio'] = parte['raw']

    elif tipo in {'precatorio_number', 'rpv_number', 'requisitorio_number'}:
        parte = _consultar_precatorio(tipo, valor, uf, tribunal)
        etapas += parte['etapas']
        pendencias += parte['pendencias']
        proxima_acao = parte['proxima_acao']
        raw_avancado['plano_precatorio'] = parte['raw']

    else:
        etapas.append(_etapa('Identificação', 'concluido', 'Tipo não mapeado especificamente — sem consulta automática pra este caso.'))
        proxima_acao = 'Não identifiquei um formato específico. Tente informar CPF, CNJ, nome, OAB, sequencial ou número de precatório/RPV.'

    resumo_partes = [f'Identifiquei "{input_texto}" como {tipo}.']
    if resultados_confirmados:
        resumo_partes.append(f'{len(resultados_confirmados)} resultado(s) confirmado(s).')
    if indicios:
        resumo_partes.append(f'{len(indicios)} indício(s) encontrado(s), confirmação oficial pendente.')
    if pendencias:
        resumo_partes.append(f'{len(pendencias)} pendência(s) — veja o que falta abaixo.')
    resumo_humano = ' '.join(resumo_partes)

    return {
        'tipo_identificado': tipo,
        'valor_normalizado': valor,
        'resumo_humano': resumo_humano,
        'consultas_realizadas': etapas,
        'resultados_confirmados': resultados_confirmados,
        'indicios': indicios,
        'pendencias': pendencias,
        'fontes_manuais_recomendadas': fontes_manuais,
        'proxima_acao_recomendada': proxima_acao or 'Confira os detalhes acima.',
        'raw_avancado': raw_avancado,
    }
