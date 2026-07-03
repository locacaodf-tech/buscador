from __future__ import annotations

import hashlib
import hmac
import time

SESSION_COOKIE_NAME = 'buscador_session'
DEFAULT_SESSION_TTL_SECONDS = 60 * 60 * 24 * 14  # 14 dias


def _sign(value: str, secret: str) -> str:
    return hmac.new(secret.encode('utf-8'), value.encode('utf-8'), hashlib.sha256).hexdigest()


def create_session_token(secret: str, ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS) -> str:
    """Gera um token de sessão assinado (HMAC-SHA256), sem dependência externa.

    Formato: "<expira_em_epoch>.<assinatura>". Não guarda estado no servidor
    (sem tabela de sessões) — a validade é só o par expiração+assinatura.
    """
    expires_at = str(int(time.time()) + ttl_seconds)
    return f'{expires_at}.{_sign(expires_at, secret)}'


def verify_session_token(token: str | None, secret: str) -> bool:
    if not token or '.' not in token:
        return False
    expires_at, _, signature = token.partition('.')
    if not expires_at.isdigit():
        return False
    if not hmac.compare_digest(_sign(expires_at, secret), signature):
        return False
    return int(expires_at) > int(time.time())
