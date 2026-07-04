from __future__ import annotations

import asyncio
from typing import Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .base import BaseConnector, SearchNotSupported, ConnectorError, ConnectorCapability
from .tribunal_registry import TRIBUNAL_ALIASES, normalize_tribunals, FEDERAL_TRIBUNALS, DEFAULT_PRECAT_TRIBUNALS
from ..config import get_settings, resolved_datajud_api_key
from ..services.precatorio import build_precatorio_query
from ..utils.cnj import normalize_cnj, infer_federal_tribunal


class DataJudConnector(BaseConnector):
    name = 'datajud'
    capabilities = (
        ConnectorCapability(
            search_type='cnj',
            required_fields=('search_key',),
            optional_fields=('tribunals', 'max_results'),
            description='Consulta processo por número CNJ na API Pública do DataJud.',
            notes='A API pública exige, na prática, número CNJ com 20 dígitos no campo numeroProcesso.',
        ),
        ConnectorCapability(
            search_type='numero_processo',
            required_fields=('search_key',),
            optional_fields=('tribunals', 'max_results'),
            description='Consulta por número de processo quando ele estiver no padrão CNJ.',
            notes='Números antigos/locais sem padrão CNJ dependem do tribunal ou de provedor privado.',
        ),
        ConnectorCapability(
            search_type='precatorio_scan',
            required_fields=(),
            optional_fields=('tribunals', 'max_results'),
            description='Varredura por classes, assuntos e movimentos com indícios de precatório/RPV.',
            notes='Não substitui consulta ao requisitório/portal de precatórios.',
        ),
    )

    def __init__(self):
        self.settings = get_settings()
        self.api_key = resolved_datajud_api_key(self.settings)
        self.base_url = self.settings.datajud_base_url.rstrip('/')
        self.headers = {
            'Authorization': f'APIKey {self.api_key}',
            'Content-Type': 'application/json',
        }

    def endpoint_for(self, tribunal: str) -> str:
        sigla = tribunal.strip().upper().replace('-', '').replace(' ', '')
        alias = TRIBUNAL_ALIASES.get(sigla)
        if not alias:
            raise ConnectorError(f'Tribunal não suportado pelo registry local: {tribunal}')
        return f'{self.base_url}/api_publica_{alias}/_search'

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError)),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _post(self, tribunal: str, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=self.settings.datajud_timeout_seconds) as client:
            response = await client.post(self.endpoint_for(tribunal), headers=self.headers, json=payload)
            if response.status_code >= 400:
                raise ConnectorError(f'DataJud {tribunal} retornou HTTP {response.status_code}: {response.text[:500]}')
            return response.json()

    async def search(self, search_type: str, search_key: str, **kwargs: Any) -> list[dict]:
        if search_type in {'cnj', 'numero_processo'}:
            tribunals = kwargs.get('tribunals')
            if not tribunals:
                # O próprio número CNJ já diz qual TRF é (dígitos J.TR) — evita
                # consultar os 6 TRFs à toa quando dá pra saber o certo.
                inferido = infer_federal_tribunal(search_key)
                tribunals = [inferido] if inferido else FEDERAL_TRIBUNALS
            return await self.search_by_cnj(search_key, tribunals, kwargs.get('max_results') or 50)
        if search_type == 'precatorio_scan':
            return await self.scan_precatorios(kwargs.get('tribunals') or DEFAULT_PRECAT_TRIBUNALS, kwargs.get('max_results') or 50)
        if search_type in {'cpf', 'cnpj', 'name', 'oab'}:
            raise SearchNotSupported(
                'A API pública do DataJud não expõe busca aberta por parte/CPF/nome. '
                'Não há fonte gratuita para isso de forma ampla; dependeria de provedor externo pago ou convênio institucional. '
                'Se for buscar por nome dentro de um precatório do STJ já carregado, use a busca por nome do STJ em vez desta.'
            )
        if search_type in {'requisitorio_number', 'precatorio_number', 'rpv_number', 'unknown'}:
            raise SearchNotSupported(
                'DataJud público não possui campo universal de número de requisitório/precatório/RPV. '
                'Alguns tribunais tratam o requisitório como processo CNJ; quando não for CNJ, é necessário conector específico do tribunal/SisPreq/PDPJ.'
            )
        raise SearchNotSupported(f'Tipo de busca não suportado no DataJud: {search_type}')

    async def search_by_cnj(self, cnj: str, tribunals: list[str] | None = None, max_results: int = 50) -> list[dict]:
        number = normalize_cnj(cnj)
        if len(number) != 20:
            raise SearchNotSupported(
                'Para DataJud, número de processo precisa estar no padrão CNJ com 20 dígitos. '
                'Números de requisitório/precatório/RPV fora desse padrão dependem de conector específico.'
            )
        target_tribunals = normalize_tribunals(tribunals, default=FEDERAL_TRIBUNALS)
        payload = {
            'size': min(max_results, self.settings.datajud_page_size),
            'query': {'match': {'numeroProcesso': number}},
        }

        async def one(sigla: str):
            try:
                data = await self._post(sigla, payload)
                return self._extract_hits(data, sigla)
            except Exception as exc:
                return [{'provider': self.name, 'tribunal': sigla, 'error': str(exc)}]

        batches = await asyncio.gather(*(one(t) for t in target_tribunals))
        return [item for batch in batches for item in batch if item]

    async def scan_precatorios(self, tribunals: list[str] | None = None, max_results: int = 50) -> list[dict]:
        target_tribunals = normalize_tribunals(tribunals, default=DEFAULT_PRECAT_TRIBUNALS)
        per_tribunal = max(1, min(self.settings.datajud_page_size, max_results // max(len(target_tribunals), 1) + 1))
        payload = build_precatorio_query(size=per_tribunal)

        async def one(sigla: str):
            try:
                data = await self._post(sigla, payload)
                return self._extract_hits(data, sigla)
            except Exception as exc:
                return [{'provider': self.name, 'tribunal': sigla, 'error': str(exc)}]

        batches = await asyncio.gather(*(one(t) for t in target_tribunals))
        return [item for batch in batches for item in batch if item][:max_results]

    def _extract_hits(self, data: dict, tribunal_hint: str) -> list[dict]:
        hits = ((data or {}).get('hits') or {}).get('hits') or []
        out = []
        for hit in hits:
            source = hit.get('_source') or {}
            source.setdefault('tribunal', source.get('tribunal') or tribunal_hint)
            out.append({'provider': self.name, 'tribunal': tribunal_hint, 'source': source, 'raw_hit': hit})
        return out
