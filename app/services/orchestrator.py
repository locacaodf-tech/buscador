from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from .normalizer import normalize_process_record
from ..connectors.base import ProviderNotConfigured, SearchNotSupported
from ..connectors.cjf_trf_precatorios import CjfTrfPrecatoriosConnector
from ..connectors.datajud import DataJudConnector
from ..connectors.mpo_siop_precatorios import MpoSiopPrecatoriosConnector
from ..connectors.stj_precatorios import StjPrecatoriosConnector
from ..connectors.tribunal_precatorios import TribunalPrecatoriosConnector
from ..models import ProcessResult, SearchLog
from ..schemas import ProcessSummary, SearchRequest, SearchResponse
from ..utils.cpf import mask_document


CONNECTOR_CLASSES = {
    'datajud': DataJudConnector,
    'tribunal_precatorios': TribunalPrecatoriosConnector,
    'cjf_trf_precatorios': CjfTrfPrecatoriosConnector,
    'stj_precatorios': StjPrecatoriosConnector,
    'mpo_siop_precatorios': MpoSiopPrecatoriosConnector,
}


class ProcessLookupOrchestrator:
    def __init__(self, db: Session):
        self.db = db

    async def search(self, request: SearchRequest) -> SearchResponse:
        search_type, search_key = request.resolved_type_and_key()
        providers = self._providers_to_try(request.provider, search_type)
        provider_label = request.provider if request.provider in {'multi', 'auto'} else providers[0]
        warnings: list[str] = request.resolution_notes()

        log = SearchLog(
            provider=provider_label,
            search_type=search_type,
            search_key_masked=mask_document(search_key),
            tribunals=json.dumps(request.tribunals, ensure_ascii=False),
            status='running',
            raw_request=request.model_dump(mode='json'),
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)

        raw_items: list[dict[str, Any]] = []
        for provider in providers:
            try:
                connector = self._connector(provider)
                if not connector.supports(search_type):
                    warnings.append(self._unsupported_message(provider, search_type))
                    continue
                items = await connector.search(
                    search_type,
                    search_key,
                    tribunals=request.tribunals,
                    max_results=request.max_results,
                    use_cache_days=request.use_cache_days,
                    extra_params=request.extra_params,
                )
                raw_items.extend(items)
                if request.provider == 'auto' and items:
                    provider_label = provider
                    break
            except ProviderNotConfigured as exc:
                warnings.append(f'{provider}: {exc}')
            except SearchNotSupported as exc:
                warnings.append(f'{provider}: {exc}')

        if not raw_items and not warnings:
            warnings.append(f'Nenhum provedor configurado suporta o identificador {search_type}. Consulte /api/capabilities e adicione o conector adequado.')

        normalized = [normalize_process_record(item, include_raw=request.include_raw) for item in raw_items if not item.get('error')]
        errors = [item for item in raw_items if item.get('error')]
        for err in errors[:10]:
            warnings.append(f"{err.get('tribunal')}: {err.get('error')}")

        if request.precatorio_only:
            normalized = [item for item in normalized if item.get('precatorio_score', 0) > 0]

        for item in normalized:
            self.db.add(ProcessResult(
                search_log_id=log.id,
                provider=item.get('provider') or provider_label,
                tribunal=item.get('tribunal'),
                numero_processo=item.get('numero_processo'),
                classe=item.get('classe'),
                assunto=item.get('assunto'),
                orgao_julgador=item.get('orgao_julgador'),
                data_ajuizamento=item.get('data_ajuizamento'),
                ultima_atualizacao=item.get('ultima_atualizacao'),
                precatorio_score=item.get('precatorio_score') or 0,
                precatorio_flags=item.get('precatorio_flags') or [],
                raw=item.get('raw'),
            ))
        log.status = 'completed'
        if warnings:
            log.notes = '\n'.join(warnings)
        self.db.commit()

        return SearchResponse(
            status='completed',
            provider_used=provider_label,
            search_type=search_type,
            search_key_masked=mask_document(search_key),
            total=len(normalized),
            results=[ProcessSummary(**item) for item in normalized],
            warnings=warnings,
        )

    def _providers_to_try(self, requested: str, search_type: str) -> list[str]:
        if requested not in {'auto', 'multi'}:
            return [requested]

        if search_type in {'cpf', 'cnpj', 'name', 'oab'}:
            # cjf_trf_precatorios ainda é experimental (ver docstring do conector),
            # por isso só entra no modo multi, não no auto por padrão.
            if requested == 'auto':
                return ['tribunal_precatorios']
            return ['tribunal_precatorios', 'cjf_trf_precatorios', 'datajud']

        if search_type in {'cnj', 'numero_processo', 'precatorio_scan'}:
            if requested == 'multi':
                return ['datajud', 'cjf_trf_precatorios']
            return ['datajud']

        if search_type in {'requisitorio_number', 'precatorio_number', 'rpv_number', 'unknown'}:
            # Esses identificadores variam por tribunal. O conector oficial é o caminho correto.
            # stj_precatorios só entra no multi (sequencial é numeração interna de cada órgão;
            # no auto, sem saber o órgão emissor, buscar sequencial no STJ geraria falso match).
            if requested == 'multi':
                return ['tribunal_precatorios', 'cjf_trf_precatorios', 'stj_precatorios', 'datajud']
            return ['tribunal_precatorios']

        if search_type == 'entidade_devedora':
            # Só o MPO/SIOP entende esse tipo de busca (confirmação orçamentária/LOA por entidade).
            return ['mpo_siop_precatorios']

        return ['datajud', 'tribunal_precatorios']

    def _connector(self, provider: str):
        cls = CONNECTOR_CLASSES.get(provider)
        if not cls:
            raise ValueError(f'Provider inválido: {provider}')
        return cls()

    def _unsupported_message(self, provider: str, search_type: str) -> str:
        cls = CONNECTOR_CLASSES[provider]
        supported = ', '.join(cap.search_type for cap in cls.capabilities) or 'nenhum'
        return f'{provider} não suporta {search_type}. Suportados: {supported}.'


def provider_capabilities() -> dict[str, dict[str, Any]]:
    return {
        name: {
            'supported_search_types': [cap.search_type for cap in cls.capabilities],
            'capabilities': {cap.search_type: cap.as_dict() for cap in cls.capabilities},
        }
        for name, cls in CONNECTOR_CLASSES.items()
    }
