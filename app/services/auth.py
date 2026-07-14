"""v36 — Serviço de autenticação real: hash de senha (bcrypt), sessão por
token opaco (não JWT — mais simples de revogar de verdade, já que
"revogação de sessões" foi pedido explicitamente: com JWT sem estado, só
dá pra "revogar" esperando expirar; com token opaco guardado em
UserSession, revogar é só marcar revoked_at)."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from ..db import get_db
from ..models_auth import User, UserSession, UserRole, usuario_tem_permissao

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')

SESSION_COOKIE_NAME = 'buscador_session'
SESSION_TTL_HOURS_DEFAULT = 24 * 14  # 14 dias — uso prático, mas revogável a qualquer momento


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def _hash_token(token: str) -> str:
    # Nunca guarda o token em claro no banco — só o hash, igual senha.
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def criar_sessao(db: Session, user: User, user_agent: str | None = None, ttl_hours: int = SESSION_TTL_HOURS_DEFAULT) -> str:
    token = secrets.token_urlsafe(32)
    sessao = UserSession(
        user_id=user.id, token_hash=_hash_token(token),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=ttl_hours),
        user_agent=user_agent,
    )
    db.add(sessao)
    db.commit()
    return token


def revogar_sessao(db: Session, token: str) -> bool:
    sessao = db.query(UserSession).filter(UserSession.token_hash == _hash_token(token)).first()
    if not sessao:
        return False
    sessao.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return True


def revogar_todas_sessoes_do_usuario(db: Session, user_id: str) -> int:
    sessoes = db.query(UserSession).filter(UserSession.user_id == user_id, UserSession.revoked_at.is_(None)).all()
    agora = datetime.now(timezone.utc)
    for s in sessoes:
        s.revoked_at = agora
    db.commit()
    return len(sessoes)


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _comparavel(dt: datetime) -> datetime:
    """SQLite devolve datetime naive (sem tzinfo); Postgres com
    DateTime(timezone=True) devolve aware. Normaliza pra aware-UTC antes
    de comparar, senão Python lança TypeError (achado real testando)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def usuario_da_sessao(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    sessao = db.query(UserSession).filter(UserSession.token_hash == _hash_token(token)).first()
    if not sessao or sessao.revoked_at is not None:
        return None
    if _comparavel(sessao.expires_at) < _agora_utc():
        return None
    user = db.query(User).filter(User.id == sessao.user_id, User.is_active.is_(True)).first()
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE_NAME) or _extrair_bearer_token(request)
    user = usuario_da_sessao(db, token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Sessão inválida ou expirada. Faça login novamente.')
    return user


def get_current_user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get(SESSION_COOKIE_NAME) or _extrair_bearer_token(request)
    return usuario_da_sessao(db, token)


def _extrair_bearer_token(request: Request) -> str | None:
    auth = request.headers.get('Authorization', '')
    if auth.lower().startswith('bearer '):
        return auth[7:].strip()
    return None


def require_permission(permissao: str):
    """Dependência FastAPI: exige que o usuário logado tenha a permissão
    efetiva pedida — checagem de verdade contra PERMISSOES_POR_PAPEL, não
    só presença de um campo 'role' no banco."""
    def _checar(current_user: User = Depends(get_current_user)) -> User:
        if not usuario_tem_permissao(current_user.role, permissao):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f'Seu papel ({current_user.role.value}) não tem permissão "{permissao}".',
            )
        return current_user
    return _checar


def require_role(*allowed_roles: UserRole):
    def _checar(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles and current_user.role != UserRole.ADMINISTRADOR:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Seu papel não tem acesso a este recurso.')
        return current_user
    return _checar
