"""v36 — Fase 1: schema do BuyerRadar trazido pra dentro do Buscador de
Processos — mesma Base, mesmo banco, tenant_id em toda entidade
operacional (pedido explícito: "mesmo existindo inicialmente apenas a
MeuPrecatórioBR, não quero que o sistema precise ser refeito").

ESCOPO DESTA RODADA (Fase 1): traz a ESTRUTURA (tabelas/campos/enums)
fiel ao BuyerRadar original, com tenant_id adicionado. NÃO traz o motor
de matching/scoring/campanha (services) — isso é Fase 2+ explicitamente,
conforme o próprio plano ("Entrega desta rodada" não lista matching nem
campanhas como entregável). Enviar campanha de verdade fica atrás de
CAMPAIGN_SENDING_ENABLED (Fase 5, ainda não implementada)."""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _novo_uuid() -> str:
    return str(uuid.uuid4())


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class _TenantMixin:
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey('tenants.id'), nullable=False, index=True)


class _TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_agora, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_agora, onupdate=_agora, nullable=False)


# ---------------------------------------------------------------------------
# Enums — fiéis ao BuyerRadar original
# ---------------------------------------------------------------------------

class OrgRole(str, enum.Enum):
    GESTORA = 'gestora'
    ADMINISTRADORA = 'administradora'
    CUSTODIANTE = 'custodiante'
    AUDITOR = 'auditor'
    CONTROLADOR = 'controlador'
    BANCO = 'banco'
    FAMILY_OFFICE = 'family_office'
    SECURITIZADORA = 'securitizadora'
    ESCRITORIO_ADVOCACIA = 'escritorio_advocacia'
    OUTRO = 'outro'


class BuyerClassification(str, enum.Enum):
    COMPRADOR_PRINCIPAL = 'comprador_principal'
    GESTOR_MANDATO_COMPRADOR = 'gestor_mandato_comprador'
    INTERMEDIARIO_ORIGINADOR = 'intermediario_originador'
    ADMINISTRADOR_CUSTODIANTE = 'administrador_custodiante'


class AssetType(str, enum.Enum):
    RPV = 'rpv'
    PRECATORIO = 'precatorio'
    DIREITO_CREDITORIO = 'direito_creditorio'


class AssetSphere(str, enum.Enum):
    FEDERAL = 'federal'
    ESTADUAL = 'estadual'
    MUNICIPAL = 'municipal'
    DISTRITAL = 'distrital'
    PRIVADA = 'privada'


class AssetNature(str, enum.Enum):
    ALIMENTAR = 'alimentar'
    COMUM = 'comum'
    TRABALHISTA = 'trabalhista'
    TRIBUTARIA = 'tributaria'
    CIVEL = 'civel'


class OpportunityPipelineStatus(str, enum.Enum):
    """Pipeline único do ativo, conforme pedido no doc original do
    BuyerRadar (processo encontrado → ... → aquisição concluída)."""
    PROCESSO_ENCONTRADO = 'processo_encontrado'
    POSSIVEL_CREDITO = 'possivel_credito'
    ANALISE_AUTOMATICA = 'analise_automatica'
    VALIDACAO_JURIDICA = 'validacao_juridica'
    ATIVO_QUALIFICADO = 'ativo_qualificado'
    COMPRADORES_IDENTIFICADOS = 'compradores_identificados'
    TEASER_APROVADO = 'teaser_aprovado'
    DISTRIBUIDO = 'distribuido'
    INTERESSADO = 'interessado'
    EM_DILIGENCIA = 'em_diligencia'
    PROPOSTA_RECEBIDA = 'proposta_recebida'
    NEGOCIACAO = 'negociacao'
    AQUISICAO_CONCLUIDA = 'aquisicao_concluida'
    SEM_ATIVO = 'sem_ativo'
    DESCARTADO = 'descartado'


class CampaignStatus(str, enum.Enum):
    RASCUNHO = 'rascunho'
    PRONTA_PARA_REVISAO = 'pronta_para_revisao'
    APROVADA = 'aprovada'
    ENVIANDO = 'enviando'
    CONCLUIDA = 'concluida'
    CANCELADA = 'cancelada'


class RecipientStatus(str, enum.Enum):
    RASCUNHO = 'rascunho'
    PRONTO = 'pronto'
    ENVIADO = 'enviado'
    ENTREGUE = 'entregue'
    ABERTO = 'aberto'
    CLICADO = 'clicado'
    RESPONDIDO = 'respondido'
    BOUNCE = 'bounce'
    RECLAMACAO = 'reclamacao'
    DESCADASTRADO = 'descadastrado'
    ERRO = 'erro'
    SUSPENSO = 'suspenso'


class SuppressionReason(str, enum.Enum):
    BOUNCE = 'bounce'
    RECLAMACAO = 'reclamacao'
    DESCADASTRO = 'descadastro'
    MANUAL = 'manual'


class ProposalStatus(str, enum.Enum):
    RECEBIDA = 'recebida'
    EM_ANALISE = 'em_analise'
    ACEITA = 'aceita'
    RECUSADA = 'recusada'
    EXPIRADA = 'expirada'
    RETIRADA = 'retirada'


# ---------------------------------------------------------------------------
# Compradores
# ---------------------------------------------------------------------------

class Organization(_TenantMixin, _TimestampMixin, Base):
    """Registro bruto de entidade (gestora/administradora/banco/etc.) —
    deliberadamente separado de BuyerProfile: nem toda organização é
    comprador (ver docstring original do BuyerRadar — evita classificar
    custodiante como comprador só por prestar serviço a um fundo)."""
    __tablename__ = 'organizations'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_novo_uuid)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    cnpj: Mapped[str | None] = mapped_column(String(18), index=True, nullable=True)
    role: Mapped[OrgRole] = mapped_column(Enum(OrgRole, native_enum=False, length=30), nullable=False)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Fund(_TenantMixin, _TimestampMixin, Base):
    """Fundos de investimento — espelha dados cadastrais da CVM quando
    importado de lá (cnpj/cd_cvm/denom_social batem com cad_fi.csv)."""
    __tablename__ = 'funds'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_novo_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), ForeignKey('organizations.id'), nullable=True, index=True)
    cnpj: Mapped[str] = mapped_column(String(18), index=True, nullable=False)
    cd_cvm: Mapped[str | None] = mapped_column(String(10), index=True, nullable=True)
    denom_social: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    classe: Mapped[str | None] = mapped_column(String(120), nullable=True)
    situacao: Mapped[str | None] = mapped_column(String(120), nullable=True)
    patrimonio_liquido: Mapped[float | None] = mapped_column(Numeric(24, 2), nullable=True)
    dt_patrimonio_liquido: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)  # 'cvm_import' | 'manual' | etc.


class BuyerProfile(_TenantMixin, _TimestampMixin, Base):
    """Curadoria: só existe quando um pesquisador decide investigar
    aquela organização como possível compradora. Score sempre recalculado
    por serviço dedicado (Fase 3+) — nunca escrito à mão diretamente
    nesta rodada."""
    __tablename__ = 'buyer_profiles'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_novo_uuid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey('organizations.id'), nullable=False, index=True)
    classification: Mapped[BuyerClassification] = mapped_column(Enum(BuyerClassification, native_enum=False, length=40), nullable=False)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # recalculado, nunca escrito à mão (Fase 3+)
    campaign_eligible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ticket_min: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    ticket_max: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    ticket_confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)  # declarado|observado|estimado|confirmado
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class BuyerMandate(_TenantMixin, _TimestampMixin, Base):
    """Um comprador pode ter várias linhas (ex.: 'RPV federal' + 'precatório
    federal'). Campo nulo = aceita qualquer valor nessa dimensão. Sem
    NENHUMA linha = compatibilidade não pode ser confirmada (nunca aceite
    implícito — mesma filosofia de nunca tratar inferência como fato)."""
    __tablename__ = 'buyer_mandates'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_novo_uuid)
    buyer_profile_id: Mapped[str] = mapped_column(String(36), ForeignKey('buyer_profiles.id'), nullable=False, index=True)
    asset_type: Mapped[AssetType | None] = mapped_column(Enum(AssetType, native_enum=False, length=30), nullable=True)
    sphere: Mapped[AssetSphere | None] = mapped_column(Enum(AssetSphere, native_enum=False, length=20), nullable=True)
    nature: Mapped[AssetNature | None] = mapped_column(Enum(AssetNature, native_enum=False, length=20), nullable=True)
    value_min: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    value_max: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    max_expected_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accepts_partial_cession: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Person(_TenantMixin, _TimestampMixin, Base):
    __tablename__ = 'people'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_novo_uuid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey('organizations.id'), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_priority_role: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Contact(_TenantMixin, _TimestampMixin, Base):
    """Um registro por pessoa. contact_ready_for_campaign sempre
    recalculado (Fase 3+) — nunca True só por existir e-mail 'inferido'."""
    __tablename__ = 'contacts'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_novo_uuid)
    person_id: Mapped[str] = mapped_column(String(36), ForeignKey('people.id'), nullable=False, unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_status: Mapped[str] = mapped_column(String(20), default='nao_validado', nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    do_not_contact: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    contact_ready_for_campaign: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


# ---------------------------------------------------------------------------
# Ativo judicial / oportunidade
# ---------------------------------------------------------------------------

class JudicialOpportunity(_TenantMixin, _TimestampMixin, Base):
    """Entidade central pedida no plano original — liga pessoa, processo
    (via source_process_cnj, referenciando o que já existe em
    OpportunityLead/BotJob), crédito, comprador, campanha. Um processo
    pode gerar nenhuma, uma ou várias oportunidades."""
    __tablename__ = 'judicial_opportunities'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_novo_uuid)
    person_id: Mapped[str | None] = mapped_column(String(36), ForeignKey('people.id'), nullable=True)
    source_opportunity_lead_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # liga em OpportunityLead.id, sem FK cross-schema forçada
    opportunity_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    asset_type: Mapped[AssetType | None] = mapped_column(Enum(AssetType, native_enum=False, length=30), nullable=True)
    judicial_sphere: Mapped[AssetSphere | None] = mapped_column(Enum(AssetSphere, native_enum=False, length=20), nullable=True)
    credit_nature: Mapped[AssetNature | None] = mapped_column(Enum(AssetNature, native_enum=False, length=20), nullable=True)
    court: Mapped[str | None] = mapped_column(String(20), nullable=True)
    judicial_unit: Mapped[str | None] = mapped_column(String(255), nullable=True)
    debtor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    process_number: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    requisition_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    face_value: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    updated_value: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    value_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_net_value: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    seller_asking_price: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    intended_percentage: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    final_judgment_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    liquidation_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    enforcement_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    requisition_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    budget_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    legal_risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)  # baixo|medio|alto
    acquisition_eligibility: Mapped[str | None] = mapped_column(String(30), nullable=True)
    acquisition_blockers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source_confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    validation_status: Mapped[str] = mapped_column(String(30), default='requer_revisao', nullable=False)
    pipeline_status: Mapped[OpportunityPipelineStatus] = mapped_column(
        Enum(OpportunityPipelineStatus, native_enum=False, length=30), default=OpportunityPipelineStatus.PROCESSO_ENCONTRADO, nullable=False,
    )
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class OpportunityFieldSource(_TenantMixin, Base):
    """Cada campo sugerido pela análise automática guarda fonte/trecho/
    confiança — pedido explícito: "não tratar inferência como fato
    confirmado". Uma linha por campo extraído."""
    __tablename__ = 'opportunity_field_sources'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_novo_uuid)
    opportunity_id: Mapped[str] = mapped_column(String(36), ForeignKey('judicial_opportunities.id'), nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_document: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    extraction_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_agora, nullable=False)


class BuyerAssetMatch(_TenantMixin, _TimestampMixin, Base):
    """Uma linha por par ativo/comprador — recalculada a cada chamada do
    motor de matching (Fase 3+, não implementado nesta rodada)."""
    __tablename__ = 'buyer_asset_matches'
    __table_args__ = (UniqueConstraint('opportunity_id', 'buyer_profile_id', name='uq_opportunity_buyer'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_novo_uuid)
    opportunity_id: Mapped[str] = mapped_column(String(36), ForeignKey('judicial_opportunities.id'), nullable=False, index=True)
    buyer_profile_id: Mapped[str] = mapped_column(String(36), ForeignKey('buyer_profiles.id'), nullable=False, index=True)
    compatibility_score: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluated_weight: Mapped[int] = mapped_column(Integer, nullable=False)
    positive_reasons: Mapped[list | None] = mapped_column(JSON, nullable=True)
    negative_reasons: Mapped[list | None] = mapped_column(JSON, nullable=True)
    unverified_criteria: Mapped[list | None] = mapped_column(JSON, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=_agora, nullable=False)


# ---------------------------------------------------------------------------
# Distribuição — estrutura pronta, ENVIO REAL desligado por padrão
# (Fase 5, ver CAMPAIGN_SENDING_ENABLED em app/config.py)
# ---------------------------------------------------------------------------

class Campaign(_TenantMixin, _TimestampMixin, Base):
    __tablename__ = 'campaigns'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_novo_uuid)
    opportunity_id: Mapped[str] = mapped_column(String(36), ForeignKey('judicial_opportunities.id'), nullable=False, index=True)
    status: Mapped[CampaignStatus] = mapped_column(Enum(CampaignStatus, native_enum=False, length=30), default=CampaignStatus.RASCUNHO, nullable=False)
    teaser_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # sem CPF/endereço/nome completo do titular/número integral do processo
    asking_price: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    asking_percentage: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class CampaignRecipient(_TenantMixin, _TimestampMixin, Base):
    """Uma linha por comprador com sua própria mensagem — nunca CC/BCC em
    massa (pedido explícito, estruturalmente garantido pelo modelo)."""
    __tablename__ = 'campaign_recipients'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_novo_uuid)
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey('campaigns.id'), nullable=False, index=True)
    buyer_profile_id: Mapped[str] = mapped_column(String(36), ForeignKey('buyer_profiles.id'), nullable=False, index=True)
    contact_id: Mapped[str | None] = mapped_column(String(36), ForeignKey('contacts.id'), nullable=True)
    status: Mapped[RecipientStatus] = mapped_column(Enum(RecipientStatus, native_enum=False, length=20), default=RecipientStatus.RASCUNHO, nullable=False)
    rendered_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rendered_body: Mapped[str | None] = mapped_column(Text, nullable=True)  # snapshot imutável — pedido explícito de auditoria


class OutboundMessage(_TenantMixin, Base):
    """Log append-only de cada TENTATIVA de envio — histórico completo,
    diferente de CampaignRecipient.status (que guarda só o estado atual)."""
    __tablename__ = 'outbound_messages'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_novo_uuid)
    campaign_recipient_id: Mapped[str] = mapped_column(String(36), ForeignKey('campaign_recipients.id'), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)  # achado real do BuyerRadar original: idempotência inadequada
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(DateTime, default=_agora, nullable=False)


class SuppressionEntry(_TenantMixin, Base):
    """Um e-mail aqui nunca mais recebe disparo automático."""
    __tablename__ = 'suppression_list'
    __table_args__ = (UniqueConstraint('tenant_id', 'email', name='uq_suppression_tenant_email'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_novo_uuid)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    reason: Mapped[SuppressionReason] = mapped_column(Enum(SuppressionReason, native_enum=False, length=20), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_agora, nullable=False)


class Proposal(_TenantMixin, _TimestampMixin, Base):
    """v36 — nova (não existia no BuyerRadar original; pedida
    explicitamente na integração: 'Criar tabela buyer_proposals')."""
    __tablename__ = 'buyer_proposals'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_novo_uuid)
    opportunity_id: Mapped[str] = mapped_column(String(36), ForeignKey('judicial_opportunities.id'), nullable=False, index=True)
    buyer_profile_id: Mapped[str] = mapped_column(String(36), ForeignKey('buyer_profiles.id'), nullable=False, index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(36), ForeignKey('campaigns.id'), nullable=True)
    proposal_value: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    proposal_percentage: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    asset_fraction: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)  # cessão parcial, em %
    payment_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    conditions_precedent: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_diligence_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    exclusivity_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    proposal_expiration: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[ProposalStatus] = mapped_column(Enum(ProposalStatus, native_enum=False, length=20), default=ProposalStatus.RECEBIDA, nullable=False)
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entered_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
