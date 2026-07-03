from __future__ import annotations

import re
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .base import BaseConnector, ConnectorCapability, ConnectorError, SearchNotSupported
from ..utils.cnj import format_cnj, normalize_cnj

# Mapa técnico das fontes federais de precatório/RPV mapeadas nesta camada.
# Levantamento completo, com fontes pesquisadas, em docs/MAPA_FONTES_PRECATORIO_FEDERAL.md.
#
# source_type:
#   dashboard_informativo - painel/página institucional, sem busca própria
#   portal_html_publico   - formulário público, sem login, confirmado ou fortemente indicado
#   portal_html_restrito  - exige login/certificado/convênio para os dados relevantes
#   roteador              - não tem sistema próprio, encaminha para outro tribunal
FEDERAL_SOURCES: dict[str, dict[str, Any]] = {
    'CJF': {
        'label': 'CJF - Conselho da Justiça Federal',
        'source_type': 'dashboard_informativo',
        'requires_credentials': False,
        'implemented': False,
        'url': 'https://www.cjf.jus.br/publico/rpvs_precatorios/',
        'notes': 'Não tem busca por processo/CPF própria. É um painel informativo (FAQ + dashboard) que linka para o portal de cada TRF.',
    },
    'TRF1': {
        'label': 'TRF1 - Consulta Processual (PJe)',
        'source_type': 'portal_html_publico',
        'requires_credentials': False,
        'implemented': True,
        'url': 'https://processual.trf1.jus.br/consultaProcessual/',
        'notes': 'Consulta pública gratuita, sem login, confirmada ao vivo por número de processo/CNJ. Também tem formulários públicos por CPF/CNPJ, nome e OAB, mapeados mas ainda não implementados aqui.',
    },
    'TRF2': {
        'label': 'TRF2 - Precatórios e RPVs',
        'source_type': 'portal_html_restrito',
        'requires_credentials': True,
        'implemented': False,
        'url': 'https://www10.trf2.jus.br/consultas/precatorio-e-rpv/',
        'notes': 'Desde a Resolução TRF2-RSP-2024/00082, precatórios/RPVs correm em segredo de justiça. Dados de pagamento só ficam visíveis para advogado credenciado com certificado digital no e-Proc.',
    },
    'TRF3': {
        'label': 'TRF3 - Requisições de Pagamento',
        'source_type': 'portal_html_publico',
        'requires_credentials': False,
        'implemented': False,
        'url': 'https://web.trf3.jus.br/consultas/internet/consultareqpag',
        'notes': 'Consulta pública por CPF/CNPJ do beneficiário + um campo adicional (OAB, processo de origem, ofício requisitório ou protocolo). Mapeada, ainda não implementada.',
    },
    'TRF4': {
        'label': 'TRF4 - Consultar Precatórios e RPVs',
        'source_type': 'portal_html_publico',
        'requires_credentials': False,
        'implemented': False,
        'url': 'https://consulta.trf4.jus.br/trf4/controlador.php?acao=pagina_precatorios',
        'notes': 'Consulta pública por CPF/CNPJ + chave (fornecida pelo tribunal/advogado), ou CPF + número do precatório/processo/requisição. A consulta processual geral do e-Proc é pública e não exige credenciamento. Mapeada, ainda não implementada.',
    },
    'TRF5': {
        'label': 'TRF5 - Portal de Precatórios/RPVs',
        'source_type': 'portal_html_publico',
        'requires_credentials': False,
        'implemented': False,
        'url': 'https://rpvprecatorio.trf5.jus.br/',
        'notes': 'Portal público: consulta individual, lista cronológica, mapa anual, dívida consolidada. Mapeada, ainda não implementada.',
    },
    'TRF6': {
        'label': 'TRF6 - Roteador PJe/eproc',
        'source_type': 'roteador',
        'requires_credentials': False,
        'implemented': False,
        'url': 'https://portal.trf6.jus.br/rpv-e-precatorios/consulta-precatorio-e-rpv/',
        'notes': 'Não tem sistema próprio: requisição transmitida via PJe é consultada no sistema do TRF1; via eproc, no eproc do TRF6. Mapeada, ainda não implementada.',
    },
}

DEFAULT_FEDERAL_TRIBUNAL = 'TRF1'
TRF1_BASE = 'https://processual.trf1.jus.br/consultaProcessual'


class CjfTrfPrecatoriosConnector(BaseConnector):
    """Camada de fontes OFICIAIS de precatório/RPV/requisitório da Justiça Federal.

    Separada de propósito do DataJud: DataJud só enxerga indício processual
    (classe/assunto/movimento indexados). Esta camada tenta consultar a fonte
    oficial de cada tribunal (CJF/TRF1-6) para dados de requisitório/orçamento,
    quando existir caminho público e sem login para isso. Status real de cada
    fonte fica em FEDERAL_SOURCES.

    Relação com app/services/official_precatorio_sources.py: aquele módulo é o
    REGISTRY declarativo (schema completo, todas as fontes mapeadas, inclusive
    as que este conector não implementa). Este arquivo é a única fonte, hoje,
    que faz uma chamada HTTP de verdade — corresponde à entrada
    'trf1_precatorios' do registry, que deve refletir isto (parcialmente
    implementada: cnj/numero_processo real, cpf/cnpj/oab/name ainda não).

    Aviso de honestidade técnica: hoje só o TRF1 tem consulta implementada
    (por número de processo/CNJ). O ambiente onde este código foi escrito não
    tem acesso de rede a *.trf1.jus.br — só a uma ferramenta de pesquisa web
    que devolve o HTML já convertido em markdown, sem os atributos de
    formulário. A URL e o fluxo de consulta por processo/CNJ foram
    confirmados ao vivo (a ferramenta de pesquisa fez a requisição de
    verdade e trouxe um resultado real). Mas esta implementação NÃO foi
    testada ponta a ponta como os conectores DataJud/Judit foram. A extração
    de campos estruturados (classe, status do requisitório, ano-orçamento)
    ainda é best-effort — devolve o texto da página, não campos garantidamente
    corretos. Valide com um caso real antes de confiar no resultado.
    """

    name = 'cjf_trf_precatorios'
    capabilities = (
        ConnectorCapability(
            'cnj',
            description='Consulta por número CNJ na fonte oficial do TRF competente.',
            notes='Implementado para TRF1 (verificado ao vivo). Demais tribunais mapeados, aguardando implementação.',
        ),
        ConnectorCapability(
            'numero_processo',
            description='Mesma consulta do CNJ, para número de processo já no padrão CNJ.',
            notes='Implementado para TRF1.',
        ),
        ConnectorCapability(
            'cpf',
            description='Consulta por CPF do beneficiário na fonte oficial, quando ela permitir.',
            notes='TRF1 tem formulário público para isso; ainda não implementado aqui (parâmetros exatos do formulário não confirmados sem inspecionar o HTML bruto).',
        ),
        ConnectorCapability(
            'cnpj',
            description='Consulta por CNPJ do beneficiário na fonte oficial, quando ela permitir.',
            notes='Mesma situação do CPF: mapeado no TRF1, não implementado.',
        ),
        ConnectorCapability(
            'oab',
            description='Consulta por OAB do advogado na fonte oficial, quando ela permitir.',
            notes='TRF1 tem formulário público para isso; mapeado, não implementado.',
        ),
        ConnectorCapability(
            'name',
            description='Consulta por nome da parte na fonte oficial, quando ela permitir.',
            notes='TRF1 tem formulário público para isso; mapeado, não implementado.',
        ),
        ConnectorCapability(
            'requisitorio_number',
            description='Consulta direta por número de requisitório.',
            notes='Nenhuma fonte mapeada tem endpoint público confirmado só para esse identificador. No TRF1, o requisitório tramita dentro do processo de origem — busque por CNJ/processo.',
        ),
        ConnectorCapability(
            'precatorio_number',
            description='Consulta direta por número de precatório.',
            notes='Mesma situação do requisitório: sem endpoint dedicado confirmado. Busque por CNJ/processo.',
        ),
        ConnectorCapability(
            'rpv_number',
            description='Consulta direta por número de RPV.',
            notes='Mesma situação: sem endpoint dedicado confirmado. Busque por CNJ/processo.',
        ),
    )

    def __init__(self):
        # Sem credencial fixa de conector: cada fonte declara se exige uma
        # (ver FEDERAL_SOURCES). Nada para validar aqui, ao contrário de
        # Judit/DataJud que exigem API key configurada.
        pass

    def _target_tribunal(self, tribunals: list[str] | None) -> str:
        if not tribunals:
            return DEFAULT_FEDERAL_TRIBUNAL
        for t in tribunals:
            sigla = t.strip().upper()
            if sigla in FEDERAL_SOURCES:
                return sigla
        return DEFAULT_FEDERAL_TRIBUNAL

    async def search(self, search_type: str, search_key: str, **kwargs: Any) -> list[dict]:
        tribunal = self._target_tribunal(kwargs.get('tribunals'))
        source = FEDERAL_SOURCES.get(tribunal)
        if not source:
            raise SearchNotSupported(
                f'Tribunal {tribunal} não está mapeado nesta camada. Mapeados: {", ".join(FEDERAL_SOURCES)}.'
            )

        if source['requires_credentials']:
            return [{
                'provider': self.name,
                'tribunal': tribunal,
                'error': (
                    f'{source["label"]} requer credencial (login de advogado com certificado digital '
                    f'ou convênio institucional) — não é possível consultar automaticamente. '
                    f'Fonte: {source["url"]}'
                ),
            }]

        if not source['implemented'] or tribunal != 'TRF1':
            return [{
                'provider': self.name,
                'tribunal': tribunal,
                'error': f'{source["label"]}: mapeada, aguardando implementação. {source["notes"]} Fonte: {source["url"]}',
            }]

        if search_type not in {'cnj', 'numero_processo'}:
            raise SearchNotSupported(
                f'Para {tribunal}, esta camada hoje só consulta por número de processo/CNJ. '
                f'Tipo pedido: "{search_type}". CPF/CNPJ/nome/OAB estão mapeados no TRF1 mas ainda não '
                'implementados aqui (parâmetros exatos do formulário não confirmados) — '
                'ver docs/MAPA_FONTES_PRECATORIO_FEDERAL.md.'
            )

        return await self._search_trf1_by_processo(search_key)

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError)),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(2),
        reraise=True,
    )
    async def _fetch(self, url: str) -> str:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(url)
            if response.status_code >= 400:
                raise ConnectorError(f'TRF1 retornou HTTP {response.status_code} para {url}')
            return response.text

    async def _search_trf1_by_processo(self, search_key: str) -> list[dict]:
        numero = normalize_cnj(search_key)
        if not numero:
            raise SearchNotSupported('Número de processo/CNJ vazio ou inválido para consulta no TRF1.')

        url = f'{TRF1_BASE}/processo.php?proc={numero}&secao=TRF1&pg=1&enviar=Pesquisar'
        try:
            html = await self._fetch(url)
        except Exception as exc:
            return [{'provider': self.name, 'tribunal': 'TRF1', 'error': f'Falha ao consultar TRF1: {exc}'}]

        text = _strip_html(html)
        not_found = bool(re.search(
            r'nenhum\s+registro|processo\s+n[aã]o\s+localizado|n[aã]o\s+foram\s+encontrados',
            text, re.IGNORECASE,
        ))
        if not_found:
            return []

        return [{
            'provider': self.name,
            'tribunal': 'TRF1',
            'source': {
                'tribunal': 'TRF1',
                'numeroProcesso': format_cnj(numero),
                'fonte_url': url,
                # Extração de campos estruturados (classe, movimentações, status do
                # requisitório) ainda não implementada — best-effort, texto bruto da
                # página para você conferir manualmente até eu confirmar o parser
                # com um caso real.
                'texto_bruto': text[:4000],
            },
            'raw_hit': {'url': url, 'html_len': len(html)},
        }]


def _strip_html(html: str) -> str:
    text = re.sub(r'<script.*?</script>', ' ', html, flags=re.S | re.I)
    text = re.sub(r'<style.*?</style>', ' ', text, flags=re.S | re.I)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = text.replace('&nbsp;', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text
