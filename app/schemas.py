from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from .services.identifier import infer_identifier, normalize_search_type
from .utils.cpf import only_digits
from .utils.cnj import normalize_cnj

SearchProvider = Literal['auto', 'multi', 'datajud', 'judit', 'tribunal_precatorios', 'cjf_trf_precatorios', 'stj_precatorios', 'mpo_siop_precatorios']
SearchType = Literal[
    'auto',
    'cnj',
    'numero_processo',
    'cpf',
    'cnpj',
    'oab',
    'name',
    'requisitorio_number',
    'precatorio_number',
    'rpv_number',
    'precatorio_scan',
    'entidade_devedora',
    'unknown',
]


class SearchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    provider: SearchProvider = 'auto'
    search_type: SearchType = 'auto'
    search_key: str | None = Field(
        default=None,
        description='Campo livre: CPF, CNPJ, OAB, nome, número CNJ, processo, requisitório, precatório ou RPV.',
    )

    # Campos específicos opcionais. O sistema usa o primeiro que vier preenchido.
    name: str | None = Field(default=None, validation_alias=AliasChoices('name', 'nome'))
    cpf: str | None = None
    cnpj: str | None = None
    oab: str | None = None
    cnj: str | None = None
    process_number: str | None = Field(default=None, validation_alias=AliasChoices('process_number', 'numero_processo', 'processo'))
    requisition_number: str | None = Field(default=None, validation_alias=AliasChoices('requisition_number', 'numero_requisitorio', 'requisitorio'))
    precatorio_number: str | None = Field(default=None, validation_alias=AliasChoices('precatorio_number', 'numero_precatorio', 'precatorio'))
    rpv_number: str | None = Field(default=None, validation_alias=AliasChoices('rpv_number', 'numero_rpv', 'rpv'))

    tribunals: list[str] = Field(default_factory=list, description='Ex.: ["TRF1", "TJDFT", "TRT10"]')
    max_results: int = Field(default=50, ge=1, le=10000)
    include_raw: bool = False
    precatorio_only: bool = False
    use_cache_days: int | None = Field(default=None, ge=0, le=365)

    # Aqui entram exigências variáveis de cada API/tribunal:
    # uf, data_nascimento, nome_mae, ano_orcamento, entidade_devedora, sistema, orgao, etc.
    extra_params: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        'search_key', 'cpf', 'cnpj', 'oab', 'cnj', 'process_number', 'requisition_number', 'precatorio_number', 'rpv_number', 'name',
        mode='before',
    )
    @classmethod
    def strip_value(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('search_type', mode='before')
    @classmethod
    def normalize_type(cls, value):
        return normalize_search_type(value)

    def resolved_type_and_key(self) -> tuple[str, str]:
        if self.search_type == 'precatorio_scan':
            return 'precatorio_scan', 'precatorio_scan'

        explicit_fields = [
            ('cnj', self.cnj),
            ('numero_processo', self.process_number),
            ('cpf', self.cpf),
            ('cnpj', self.cnpj),
            ('oab', self.oab),
            ('requisitorio_number', self.requisition_number),
            ('precatorio_number', self.precatorio_number),
            ('rpv_number', self.rpv_number),
            ('name', self.name),
        ]
        for field_type, value in explicit_fields:
            if value:
                if field_type in {'cpf', 'cnpj'}:
                    return field_type, only_digits(value)
                if field_type == 'cnj':
                    return 'cnj', normalize_cnj(value)
                if field_type == 'numero_processo':
                    digits = normalize_cnj(value)
                    return ('cnj', digits) if len(digits) == 20 else ('numero_processo', value.strip())
                return field_type, value.strip()

        if self.search_key:
            resolved = infer_identifier(self.search_key, self.search_type)
            return resolved.search_type, resolved.search_key

        raise ValueError('Informe search_key ou algum campo específico: cpf, cnpj, nome, cnj, processo, requisitório, precatório ou RPV.')

    def resolution_notes(self) -> list[str]:
        if not self.search_key:
            return []
        resolved = infer_identifier(self.search_key, self.search_type)
        return list(resolved.notes)


class CapabilityResponse(BaseModel):
    providers: dict[str, dict[str, Any]]
    message: str


class ProcessSummary(BaseModel):
    provider: str
    tribunal: str | None = None
    numero_processo: str | None = None
    classe: str | None = None
    assunto: str | None = None
    orgao_julgador: str | None = None
    data_ajuizamento: str | None = None
    ultima_atualizacao: str | None = None
    precatorio_score: int = 0
    precatorio_flags: list[str] = Field(default_factory=list)
    raw: dict | None = None


class SearchResponse(BaseModel):
    status: str
    provider_used: str
    search_type: str
    search_key_masked: str
    total: int
    results: list[ProcessSummary]
    warnings: list[str] = Field(default_factory=list)


class OfficialPrecatorioPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    search_type: str = 'auto'
    search_key: str
    extra_params: dict[str, Any] = Field(default_factory=dict)

    @field_validator('search_key', mode='before')
    @classmethod
    def strip_plan_key(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('search_type', mode='before')
    @classmethod
    def normalize_plan_type(cls, value):
        return normalize_search_type(value) if value else 'auto'

    def resolved_type_and_key(self) -> tuple[str, str]:
        if self.search_type and self.search_type != 'auto':
            return self.search_type, self.search_key
        resolved = infer_identifier(self.search_key, self.search_type)
        return resolved.search_type, resolved.search_key


class BrowserSearchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_id: str
    search_type: str = 'auto'
    search_key: str
    extra_params: dict[str, Any] = Field(default_factory=dict)

    @field_validator('search_key', mode='before')
    @classmethod
    def strip_browser_key(cls, value):
        return value.strip() if isinstance(value, str) else value


class DossierRequest(SearchRequest):
    """Pedido de dossiê completo.

    Herda a busca processual já existente e adiciona a intenção de montar camadas
    oficiais de precatório/RPV/LOA. A resposta pode conter fontes não implementadas
    como plano/pendência, em vez de inventar dados.
    """

    include_official_precatorio: bool = True
    include_budget_loa: bool = True
    include_commercial_score: bool = True


class StjSearchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    search_type: Literal['sequencial', 'precatorio_number', 'requisitorio_number', 'rpv_number', 'cnj', 'numero_processo', 'name'] = 'sequencial'
    search_key: str
    ano_orcamento: int | None = None

    @field_validator('search_key', mode='before')
    @classmethod
    def strip_stj_key(cls, value):
        return value.strip() if isinstance(value, str) else value


class CertificatePlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    document: str | None = None
    certificate_types: list[str] = Field(default_factory=list)


class CertificateRequestInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_id: str
    certificate_type: str
    document: str | None = None
    name: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class PortalAutomationStartRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_id: str
    url: str
    fill_fields: dict[str, str] = Field(default_factory=dict)
    submit_selector: str


class PortalAutomationSolveRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    captcha_text: str


class DiligenciaRequest(BaseModel):
    """Requisição do Motor Operacional de Diligência (v28) — recebe
    qualquer dado digitado, sem o cliente precisar saber qual endpoint/
    conector usar."""
    model_config = ConfigDict(populate_by_name=True)

    input: str
    uf: str | None = None
    tribunal: str | None = None
    objetivo: Literal['completo', 'processo', 'precatorio', 'certidao'] = 'completo'
    # Opcional (v30.1): se True, também aciona a camada de bots (mesmo
    # runner de /api/bots/run) e devolve job_id junto — sem quebrar quem já
    # chama /api/diligencia sem esse campo (default False = comportamento
    # de sempre, inalterado).
    run_bots: bool = False

    @field_validator('input', mode='before')
    @classmethod
    def strip_input(cls, value):
        return value.strip() if isinstance(value, str) else value


class BotsRunRequest(BaseModel):
    """Requisição da camada de bots executores (v30)."""
    model_config = ConfigDict(populate_by_name=True)

    input: str
    uf: str | None = None
    tribunal: str | None = None
    objetivo: Literal['completo', 'processo', 'precatorio', 'certidao'] = 'completo'
    # Opcional: aciona o PortalBot contra um alvo real (URL + seletores).
    # Sem isso, o PortalBot não roda sozinho — ele precisa de seletores de
    # campo confirmados por quem tem acesso de navegador ao portal (ver
    # app/bots/portal_bot.py para o porquê disso ser deliberado).
    portal_url: str | None = None
    portal_fill_fields: dict[str, str] | None = None
    portal_submit_selector: str | None = None
    portal_source_id: str | None = None

    @field_validator('input', mode='before')
    @classmethod
    def strip_input(cls, value):
        return value.strip() if isinstance(value, str) else value


class BotsResumeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    captcha_text: str
