from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Any


class ConnectorError(Exception):
    pass


class ProviderNotConfigured(ConnectorError):
    pass


class SearchNotSupported(ConnectorError):
    pass


@dataclass(frozen=True)
class ConnectorCapability:
    search_type: str
    required_fields: tuple[str, ...] = ('search_key',)
    optional_fields: tuple[str, ...] = ('tribunals', 'max_results')
    description: str = ''
    notes: str = ''

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data['required_fields'] = list(self.required_fields)
        data['optional_fields'] = list(self.optional_fields)
        return data


class BaseConnector(ABC):
    name: str
    capabilities: tuple[ConnectorCapability, ...] = ()

    def supports(self, search_type: str) -> bool:
        return any(cap.search_type == search_type for cap in self.capabilities)

    def capability_map(self) -> dict[str, dict[str, Any]]:
        return {cap.search_type: cap.as_dict() for cap in self.capabilities}

    @abstractmethod
    async def search(self, search_type: str, search_key: str, **kwargs: Any) -> list[dict]:
        raise NotImplementedError
