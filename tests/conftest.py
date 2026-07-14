"""v36 — Isolamento entre testes: a tabela de usuários é compartilhada
(mesmo banco SQLite pra toda a suíte, sem transação por teste). Sem isso,
um teste que cria um User real "vaza" pros próximos — de repente
qualquer rota passa a exigir login, quebrando dezenas de testes que não
têm nada a ver com autenticação (achado real, testando: 29 testes
quebraram em cascata na primeira rodada depois de introduzir User)."""
import os

os.environ.setdefault('APP_LOGIN_PASSWORD', '')
os.environ.setdefault('INTERNAL_API_TOKEN', '')

import pytest

from app.db import init_db, SessionLocal

init_db()


@pytest.fixture(autouse=True)
def _limpar_usuarios_entre_testes():
    """Roda antes de CADA teste — garante estado limpo, independente da
    ordem de execução dos arquivos. Testes que precisam de um usuário
    real (ex.: test_main_routes.py, test_admin_users.py) criam o próprio
    dentro do teste; este fixture só impede que ele sobreviva pro próximo."""
    db = SessionLocal()
    try:
        from app.models_auth import User, UserSession, Tenant, AuditLogEntry
        db.query(UserSession).delete()
        db.query(AuditLogEntry).delete()
        db.query(User).delete()
        db.query(Tenant).delete()
        db.commit()
    finally:
        db.close()
    yield
