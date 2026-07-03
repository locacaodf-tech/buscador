from __future__ import annotations

from typing import Any

from .base import BaseConnector, ConnectorCapability, ProviderNotConfigured


class TribunalPrecatoriosConnector(BaseConnector):
    """Contrato/base para APIs oficiais de precatórios dos tribunais.

    Esta classe não consulta nenhum tribunal sozinha. Ela documenta o ponto certo
    para plugar SisPreq/PDPJ, TRF1, TRF2, TRF3, TRF4, TRF5, TRF6, CJF ou portais
    estaduais quando você tiver credenciais, endpoint e regras de uso.
    """

    name = 'tribunal_precatorios'
    capabilities = (
        ConnectorCapability(
            'requisitorio_number',
            required_fields=('search_key', 'extra_params.tribunal'),
            optional_fields=('extra_params.cpf', 'extra_params.nome', 'extra_params.ano_orcamento', 'extra_params.entidade_devedora'),
            description='Consulta por número de requisitório quando a API do tribunal aceitar esse identificador.',
            notes='Cada tribunal define formato e campos obrigatórios.',
        ),
        ConnectorCapability(
            'precatorio_number',
            required_fields=('search_key', 'extra_params.tribunal'),
            optional_fields=('extra_params.cpf', 'extra_params.nome', 'extra_params.ano_orcamento', 'extra_params.entidade_devedora'),
            description='Consulta por número de precatório quando a API do tribunal aceitar esse identificador.',
            notes='Alguns tribunais usam número do requisitório; outros usam CNJ do processo de precatório.',
        ),
        ConnectorCapability(
            'rpv_number',
            required_fields=('search_key', 'extra_params.tribunal'),
            optional_fields=('extra_params.cpf', 'extra_params.nome', 'extra_params.entidade_devedora'),
            description='Consulta por número de RPV quando a API do tribunal aceitar esse identificador.',
            notes='Frequentemente exige tribunal, CPF/CNPJ do beneficiário ou processo originário.',
        ),
        ConnectorCapability(
            'cpf',
            required_fields=('search_key', 'extra_params.tribunal'),
            optional_fields=('extra_params.nome', 'extra_params.ano_orcamento'),
            description='Consulta de precatórios/RPVs por CPF do beneficiário quando o tribunal/API permitir.',
            notes='Pode exigir autenticação, perfil institucional ou convênio.',
        ),
    )

    def __init__(self):
        raise ProviderNotConfigured(
            'Conector tribunal_precatorios é um contrato de integração. Configure uma implementação real para o tribunal/SisPreq/PDPJ escolhido.'
        )

    async def search(self, search_type: str, search_key: str, **kwargs: Any) -> list[dict]:
        raise ProviderNotConfigured('Nenhuma API oficial de precatórios foi configurada para este conector.')
