from __future__ import annotations

import asyncio
from typing import Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .base import BaseConnector, ProviderNotConfigured, ConnectorError, ConnectorCapability
from ..config import get_settings

JUDIT_SEARCH_TYPES = {'cpf', 'cnpj', 'oab', 'cnj', 'name'}

# Mapeamento explícito interno -> externo (payload enviado à Judit).
# cpf/cnpj/oab/cnj: a doc disponível confirma o valor literal.
# name: a doc só mostra exemplo com "cpf"; não fica 100% claro se o valor
# para busca por nome é "name" ou "nome". Por isso NÃO tem entrada fixa aqui
# — é resolvido em tempo de execução por JuditConnector.external_search_type()
# usando JUDIT_NAME_SEARCH_TYPE (configurável no .env, default "name").
JUDIT_TYPE_MAP = {
    'cpf': 'cpf',
    'cnpj': 'cnpj',
    'oab': 'oab',
    'cnj': 'cnj',
}

# Campos que, quando vierem em extra_params, são tratados como filtros estruturados
# de search_params.filter em vez de irem soltos no corpo da busca.
JUDIT_FILTER_FIELDS = ('side', 'amount_gte', 'distribution_date_gte')


class JuditConnector(BaseConnector):
    """Conector para busca de processos via Judit (CPF, CNPJ, OAB, CNJ e nome).

    Autenticação exclusivamente por header ``api-key``. Nunca usar
    ``Authorization: Bearer`` — essa integração é especificada para funcionar
    somente com ``api-key``, conforme instrução explícita do usuário.

    Fluxo assíncrono padrão:
    - POST {JUDIT_REQUESTS_BASE_URL}/requests
    - GET  {JUDIT_REQUESTS_BASE_URL}/requests/{id}
    - GET  {JUDIT_REQUESTS_BASE_URL}/responses

    JUDIT_TRACKING_BASE_URL e JUDIT_LAWSUITS_BASE_URL ficam disponíveis em
    config para funcionalidades futuras (monitoramento contínuo / consulta
    síncrona direto do datalake). Não implementadas nesta versão porque não
    fazem parte do fluxo de busca pontual pedido aqui.
    """

    name = 'judit'
    capabilities = (
        ConnectorCapability('cpf', description='Busca processual por CPF via Judit.'),
        ConnectorCapability('cnpj', description='Busca processual por CNPJ via Judit.'),
        ConnectorCapability('oab', optional_fields=('tribunals', 'max_results', 'extra_params.uf'), description='Busca por OAB via Judit.', notes='Alguns provedores exigem UF separada da OAB.'),
        ConnectorCapability('cnj', description='Busca por número CNJ via Judit.'),
        ConnectorCapability('name', description='Busca por nome da parte via Judit.', notes='Pode retornar homônimos; considere usar extra_params para reduzir ambiguidade.'),
    )

    def __init__(self):
        self.settings = get_settings()
        self.api_key = self.settings.judit_api_key
        if not self.settings.judit_enabled or not self.api_key:
            raise ProviderNotConfigured('Judit não está habilitada. Configure JUDIT_ENABLED=true e JUDIT_API_KEY.')
        self.requests_base = self.settings.judit_requests_base_url.rstrip('/')
        self.tracking_base = self.settings.judit_tracking_base_url.rstrip('/')
        self.lawsuits_base = self.settings.judit_lawsuits_base_url.rstrip('/')

    def _headers(self) -> dict[str, str]:
        return {'api-key': self.api_key, 'Content-Type': 'application/json'}

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError)),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _request(self, method: str, url: str, **kwargs) -> dict:
        async with httpx.AsyncClient(timeout=self.settings.judit_timeout_seconds) as client:
            response = await client.request(method, url, headers=self._headers(), **kwargs)
            if response.status_code >= 400:
                raise ConnectorError(f'Judit HTTP {response.status_code}: {response.text[:500]}')
            if not response.text:
                return {}
            return response.json()

    async def search(self, search_type: str, search_key: str, **kwargs: Any) -> list[dict]:
        if search_type not in JUDIT_SEARCH_TYPES:
            raise ConnectorError(
                f'Tipo de busca não suportado na Judit: {search_type}. '
                f'Suportados aqui: {", ".join(sorted(JUDIT_SEARCH_TYPES))}. '
                'Para requisitório/precatório/RPV, use tribunal_precatorios ou DataJud.'
            )
        try:
            request_id = await self.create_request(search_type, search_key, kwargs)
            request_data = await self.poll_request(request_id)
            responses = await self.get_responses(request_id=request_id)
            return self._normalize_responses(responses, request_id=request_id, request_data=request_data)
        except Exception as exc:
            # Mesmo padrão do DataJud: falha de rede/HTTP vira item de erro, não
            # exceção não tratada. O orchestrator já sabe ler item.get('error').
            return [{'provider': self.name, 'tribunal': None, 'error': str(exc)}]

    @staticmethod
    def external_search_type(internal_type: str) -> str:
        """Traduz o search_type interno (identifier.py) para o valor enviado à Judit.

        cpf/cnpj/oab/cnj usam o mapeamento fixo de JUDIT_TYPE_MAP. Para 'name',
        o valor vem de JUDIT_NAME_SEARCH_TYPE (default 'name'), já que a doc
        disponível não confirma explicitamente se o termo é "name" ou "nome".
        """
        if internal_type == 'name':
            return get_settings().judit_name_search_type
        return JUDIT_TYPE_MAP.get(internal_type, internal_type)

    @staticmethod
    def build_search_payload(search_type: str, search_key: str, options: dict | None = None) -> dict:
        """Monta o payload de POST /requests. Função pura (sem chamada de rede) para facilitar teste.

        search_type aqui é sempre o valor INTERNO do projeto (cpf/cnpj/oab/cnj/name).
        A tradução para o valor externo enviado à Judit acontece via
        external_search_type() antes de montar o payload.

        Suporta:
        - cache_ttl_in_days (topo do payload);
        - search_params.filter.tribunals.keys (via options['tribunals']);
        - search_params.filter.side / amount_gte / distribution_date_gte
          (via options['extra_params']);
        - quaisquer outros campos livres em options['extra_params'] são
          enviados diretamente em search_params (ex.: uf, data_nascimento).
        """
        options = options or {}
        payload: dict[str, Any] = {
            'search': {
                'search_type': JuditConnector.external_search_type(search_type),
                'search_key': search_key,
            }
        }
        if options.get('use_cache_days') is not None:
            payload['cache_ttl_in_days'] = options['use_cache_days']

        extra_params = dict(options.get('extra_params') or {})

        filter_fields: dict[str, Any] = {}
        if options.get('tribunals'):
            filter_fields['tribunals'] = {'keys': options['tribunals'], 'not_equal': False}
        for key in JUDIT_FILTER_FIELDS:
            if key in extra_params:
                filter_fields[key] = extra_params.pop(key)

        search_params: dict[str, Any] = {}
        if filter_fields:
            search_params['filter'] = filter_fields
        if extra_params:
            # Campo livre para exigências específicas: UF da OAB, data de nascimento,
            # nome da mãe, sistema de origem etc.
            search_params.update(extra_params)
        if search_params:
            payload['search']['search_params'] = search_params

        return payload

    async def create_request(self, search_type: str, search_key: str, options: dict | None = None) -> str:
        payload = self.build_search_payload(search_type, search_key, options)
        data = await self._request('POST', f'{self.requests_base}/requests', json=payload)
        request_id = data.get('id') or data.get('request_id') or data.get('_id')
        if not request_id:
            # algumas respostas podem encapsular em data
            request_id = ((data.get('data') or {}).get('id') or (data.get('data') or {}).get('request_id'))
        if not request_id:
            raise ConnectorError(f'Não localizei request_id na resposta da Judit: {data}')
        return str(request_id)

    async def poll_request(self, request_id: str) -> dict:
        last_data: dict = {}
        for _ in range(self.settings.judit_max_polls):
            data = await self._request('GET', f'{self.requests_base}/requests/{request_id}')
            last_data = data
            status = str(data.get('status') or (data.get('data') or {}).get('status') or '').lower()
            if status in {'completed', 'complete', 'success', 'done', 'finished'}:
                return data
            if status in {'failed', 'error', 'canceled', 'cancelled'}:
                raise ConnectorError(f'Requisição Judit falhou: {data}')
            await asyncio.sleep(self.settings.judit_poll_seconds)
        return last_data

    async def get_responses(self, request_id: str | None = None, page: int = 1) -> dict:
        url = f'{self.requests_base}/responses?page={page}'
        if request_id:
            url += f'&request_id={request_id}'
        return await self._request('GET', url)

    def _normalize_responses(self, responses: dict, request_id: str, request_data: dict) -> list[dict]:
        # Flexível para formatos diferentes: list direto, data/items/results etc.
        items: Any = responses
        for key in ('data', 'items', 'results', 'responses'):
            if isinstance(items, dict) and key in items:
                items = items[key]
                break
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            items = []
        out = []
        for item in items:
            if not isinstance(item, dict):
                continue
            out.append({'provider': self.name, 'tribunal': item.get('tribunal'), 'source': item, 'raw_hit': item})
        if not out:
            out.append({'provider': self.name, 'tribunal': None, 'source': {'request_id': request_id, 'request': request_data, 'responses': responses}, 'raw_hit': responses})
        return out
