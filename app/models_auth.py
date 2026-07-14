"""v36 — Fase 1: multiusuário real, com tenant e permissões efetivas.

Substitui o gate de senha única (APP_LOGIN_PASSWORD) por usuários
individuais, com papel e permissões de verdade — não só um nome de papel
guardado no banco sem checagem nenhuma (achado real auditando o
BuyerRadar: o registro era público e aceitava qualquer role escolhida
pelo próprio requisitante; aqui o cadastro de usuário NUNCA é público —
só administrador cria usuário, e o primeiro administrador só nasce via
comando CLI de bootstrap)."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _novo_uuid() -> str:
    return str(uuid.uuid4())


class UserRole(str, enum.Enum):
    ADMINISTRADOR = 'administrador'
    PESQUISADOR = 'pesquisador'
    JURIDICO = 'juridico'
    COMERCIAL = 'comercial'
    APROVADOR = 'aprovador'
    VISUALIZADOR = 'visualizador'


class Tenant(Base):
    """Organização operacional. Só existe uma hoje (MeuPrecatórioBR), mas
    a estrutura já nasce pronta pra múltiplas — nenhuma entidade
    operacional roda sem tenant_id, mesmo quando só há um tenant."""
    __tablename__ = 'tenants'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_novo_uuid)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class User(Base):
    """Usuário individual — substitui o gate de senha compartilhada.
    Nunca criado por endpoint público; só por administrador autenticado
    ou pelo comando de bootstrap (primeiro admin)."""
    __tablename__ = 'users'
    __table_args__ = (UniqueConstraint('tenant_id', 'email', name='uq_user_tenant_email'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_novo_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey('tenants.id'), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, native_enum=False, length=32), default=UserRole.VISUALIZADOR, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    def can_change_role_of(self, alvo: 'User') -> bool:
        """Nenhum usuário pode alterar o próprio papel — nem administrador."""
        return self.role == UserRole.ADMINISTRADOR and self.id != alvo.id


class UserSession(Base):
    """Sessão de login — permite revogar sessões individualmente (pedido
    explícito: 'revogação de sessões' faz parte do controle do admin)."""
    __tablename__ = 'user_sessions'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_novo_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)


class AuditLogEntry(Base):
    """Registro de auditoria — pedido explícito no item 8 (papéis) e no
    item 6 (campanhas: 'registro de auditoria'). Genérico o suficiente
    pra cobrir qualquer ação sensível, não só campanhas."""
    __tablename__ = 'audit_log_entries'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_novo_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict | None] = mapped_column(__import__('sqlalchemy').JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


# ---------------------------------------------------------------------------
# Matriz de permissões — efetiva, checada de verdade em cada rota
# protegida, não só um nome de papel guardado sem checagem (achado real
# no BuyerRadar original).
# ---------------------------------------------------------------------------

PERMISSOES_POR_PAPEL: dict[UserRole, set[str]] = {
    UserRole.ADMINISTRADOR: {'*'},  # administrador gerencia toda a plataforma
    UserRole.PESQUISADOR: {
        'busca:executar', 'processos:ler', 'compradores:ler', 'fontes:ler',
        'ativos:ler', 'watchers:executar',
    },
    UserRole.JURIDICO: {
        'processos:ler', 'ativos:ler', 'ativos:validar_juridico', 'ativos:avaliar_risco',
        'ativos:definir_elegibilidade', 'compradores:ler',
    },
    UserRole.COMERCIAL: {
        'processos:ler', 'ativos:ler', 'compradores:ler', 'compradores:gerenciar',
        'contatos:gerenciar', 'campanhas:criar', 'campanhas:editar', 'negociacoes:gerenciar',
        'propostas:gerenciar',
    },
    UserRole.APROVADOR: {
        'processos:ler', 'ativos:ler', 'compradores:ler', 'campanhas:ler', 'campanhas:aprovar',
    },
    UserRole.VISUALIZADOR: {
        'processos:ler', 'ativos:ler', 'compradores:ler', 'campanhas:ler', 'fontes:ler',
    },
}


def usuario_tem_permissao(role: UserRole, permissao: str) -> bool:
    permissoes = PERMISSOES_POR_PAPEL.get(role, set())
    return '*' in permissoes or permissao in permissoes
