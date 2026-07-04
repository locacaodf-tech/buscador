"""Interface preparada para um futuro provider comercial de busca nacional
por pessoa (Judit, Escavador, Jusbrasil ou outro). NÃO implementado nesta
versão — só a forma, pra não travar quando/se um dia for plugado.

O conector real da Judit já existe em app/connectors/judit.py e continua
funcionando via /api/search (provider=judit) para quem quiser usar hoje.
Esta interface é sobre o FUTURO: um jeito único de trocar de provider sem
reescrever o motor de diligência."""
from __future__ import annotations

from typing import Any, Protocol


class CommercialProvider(Protocol):
    """Qualquer provider comercial de busca processual nacional deveria
    implementar esta forma. Nenhum provider é obrigatório — o motor de
    diligência funciona sem nenhum, usando DataJud/STJ/fontes oficiais."""

    name: str

    def is_configured(self) -> bool:
        ...

    async def search_by_cpf(self, cpf: str, **kwargs: Any) -> list[dict]:
        ...

    async def search_by_cnpj(self, cnpj: str, **kwargs: Any) -> list[dict]:
        ...

    async def search_by_name(self, name: str, **kwargs: Any) -> list[dict]:
        ...

    async def search_by_oab(self, oab: str, uf: str | None = None, **kwargs: Any) -> list[dict]:
        ...

    async def search_by_cnj(self, cnj: str, **kwargs: Any) -> list[dict]:
        ...
