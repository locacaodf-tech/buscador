"""v36 — Fase 1: multiusuário real, tenant, permissões. Cobre exatamente
os pontos pedidos: nenhum usuário altera o próprio papel, isolamento por
tenant, permissões efetivas por papel (não só nome guardado no banco)."""
import os

os.environ.setdefault('APP_LOGIN_PASSWORD', '')
os.environ.setdefault('INTERNAL_API_TOKEN', '')

from fastapi.testclient import TestClient

from app.main import app
from app.db import init_db, SessionLocal
from app.models_auth import Tenant, User, UserRole
from app.services.auth import hash_password, criar_sessao

init_db()


def _criar_tenant(slug='meuprecatoriobr', nome='MeuPrecatórioBR'):
    db = SessionLocal()
    tenant = db.query(Tenant).filter(Tenant.slug == slug).first()
    if not tenant:
        tenant = Tenant(slug=slug, nome=nome)
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
    db.close()
    return tenant.id


def _criar_usuario(tenant_id, email, role, senha='senhaDeTeste!123'):
    db = SessionLocal()
    user = User(tenant_id=tenant_id, email=email, full_name=email.split('@')[0], hashed_password=hash_password(senha), role=role, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id  # captura ANTES de criar_sessao, que comita de novo e expira os atributos
    token = criar_sessao(db, user)
    db.close()
    return user_id, token


def _client_logado(token):
    client = TestClient(app)
    client.cookies.set('buscador_session', token)
    return client


# ---------------------------------------------------------------------------
# Permissões efetivas — cada papel só acessa o que pode, de verdade
# ---------------------------------------------------------------------------

def test_administrador_acessa_gestao_de_usuarios():
    tenant_id = _criar_tenant()
    _, token = _criar_usuario(tenant_id, 'admin1@meuprecatoriobr.com.br', UserRole.ADMINISTRADOR)
    client = _client_logado(token)
    resp = client.get('/api/admin/users')
    assert resp.status_code == 200


def test_pesquisador_nao_acessa_gestao_de_usuarios():
    tenant_id = _criar_tenant()
    _, token = _criar_usuario(tenant_id, 'pesq1@meuprecatoriobr.com.br', UserRole.PESQUISADOR)
    client = _client_logado(token)
    resp = client.get('/api/admin/users')
    assert resp.status_code == 403


def test_juridico_nao_acessa_gestao_de_usuarios():
    tenant_id = _criar_tenant()
    _, token = _criar_usuario(tenant_id, 'jur1@meuprecatoriobr.com.br', UserRole.JURIDICO)
    client = _client_logado(token)
    resp = client.get('/api/admin/users')
    assert resp.status_code == 403


def test_visualizador_nao_acessa_gestao_de_usuarios():
    tenant_id = _criar_tenant()
    _, token = _criar_usuario(tenant_id, 'vis1@meuprecatoriobr.com.br', UserRole.VISUALIZADOR)
    client = _client_logado(token)
    resp = client.get('/api/admin/users')
    assert resp.status_code == 403


def test_todos_os_papeis_tem_permissoes_diferentes_de_administrador():
    from app.models_auth import PERMISSOES_POR_PAPEL
    permissoes_admin = PERMISSOES_POR_PAPEL[UserRole.ADMINISTRADOR]
    for papel in [UserRole.PESQUISADOR, UserRole.JURIDICO, UserRole.COMERCIAL, UserRole.APROVADOR, UserRole.VISUALIZADOR]:
        assert PERMISSOES_POR_PAPEL[papel] != permissoes_admin
        assert 'admin:usuarios' not in PERMISSOES_POR_PAPEL[papel]


# ---------------------------------------------------------------------------
# Nenhum usuário altera o próprio papel
# ---------------------------------------------------------------------------

def test_administrador_nao_pode_alterar_o_proprio_papel():
    tenant_id = _criar_tenant()
    user_id, token = _criar_usuario(tenant_id, 'admin2@meuprecatoriobr.com.br', UserRole.ADMINISTRADOR)
    client = _client_logado(token)
    resp = client.patch(f'/api/admin/users/{user_id}', json={'role': 'visualizador'})
    assert resp.status_code == 403


def test_administrador_pode_alterar_papel_de_outro_usuario():
    tenant_id = _criar_tenant()
    _, token_admin = _criar_usuario(tenant_id, 'admin3@meuprecatoriobr.com.br', UserRole.ADMINISTRADOR)
    outro_id, _ = _criar_usuario(tenant_id, 'outro1@meuprecatoriobr.com.br', UserRole.VISUALIZADOR)
    client = _client_logado(token_admin)
    resp = client.patch(f'/api/admin/users/{outro_id}', json={'role': 'pesquisador'})
    assert resp.status_code == 200
    assert resp.json()['role'] == 'pesquisador'


def test_administrador_nao_pode_desativar_a_si_mesmo():
    tenant_id = _criar_tenant()
    user_id, token = _criar_usuario(tenant_id, 'admin4@meuprecatoriobr.com.br', UserRole.ADMINISTRADOR)
    client = _client_logado(token)
    resp = client.patch(f'/api/admin/users/{user_id}', json={'is_active': False})
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Nenhum cadastro público — só admin cria usuário
# ---------------------------------------------------------------------------

def test_criar_usuario_exige_autenticacao():
    client = TestClient(app)
    resp = client.post('/api/admin/users', json={'email': 'x@x.com', 'full_name': 'X', 'password': 'senha123456!', 'role': 'visualizador'})
    assert resp.status_code == 401


def test_nao_existe_endpoint_de_registro_publico():
    """Achado real de auditoria no BuyerRadar original: /api/auth/register
    era público e aceitava qualquer role do próprio requisitante. Aqui
    esse endpoint nunca existiu — confirma que a rota não existe."""
    client = TestClient(app)
    resp = client.post('/api/auth/register', json={'email': 'invasor@x.com', 'password': 'x', 'role': 'administrador'})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Isolamento por tenant
# ---------------------------------------------------------------------------

def test_admin_de_um_tenant_nao_ve_usuarios_de_outro_tenant():
    tenant_a = _criar_tenant('tenant-a', 'Tenant A')
    tenant_b = _criar_tenant('tenant-b', 'Tenant B')
    _, token_a = _criar_usuario(tenant_a, 'admin_a@x.com', UserRole.ADMINISTRADOR)
    _criar_usuario(tenant_b, 'admin_b@x.com', UserRole.ADMINISTRADOR)

    client_a = _client_logado(token_a)
    resp = client_a.get('/api/admin/users')
    emails = [u['email'] for u in resp.json()]
    assert 'admin_a@x.com' in emails
    assert 'admin_b@x.com' not in emails


def test_admin_de_um_tenant_nao_altera_usuario_de_outro_tenant():
    tenant_a = _criar_tenant('tenant-c', 'Tenant C')
    tenant_b = _criar_tenant('tenant-d', 'Tenant D')
    _, token_a = _criar_usuario(tenant_a, 'admin_c@x.com', UserRole.ADMINISTRADOR)
    user_b_id, _ = _criar_usuario(tenant_b, 'user_d@x.com', UserRole.VISUALIZADOR)

    client_a = _client_logado(token_a)
    resp = client_a.patch(f'/api/admin/users/{user_b_id}', json={'role': 'administrador'})
    assert resp.status_code == 404  # não encontra — não vaza nem confirma que existe em outro tenant


def test_mesmo_email_pode_existir_em_tenants_diferentes():
    tenant_a = _criar_tenant('tenant-e', 'Tenant E')
    tenant_b = _criar_tenant('tenant-f', 'Tenant F')
    _criar_usuario(tenant_a, 'repetido@x.com', UserRole.VISUALIZADOR)
    # não deve estourar erro de unicidade — o unique constraint é (tenant_id, email), não só email
    user_id_b, _ = _criar_usuario(tenant_b, 'repetido@x.com', UserRole.VISUALIZADOR)
    assert user_id_b is not None


# ---------------------------------------------------------------------------
# Sessão: revogação de verdade
# ---------------------------------------------------------------------------

def test_revogar_sessao_invalida_o_cookie_na_hora():
    tenant_id = _criar_tenant()
    _, token = _criar_usuario(tenant_id, 'revogavel@meuprecatoriobr.com.br', UserRole.ADMINISTRADOR)
    client = _client_logado(token)
    assert client.get('/api/me').status_code == 200

    client.get('/logout')
    resp = client.get('/api/me')
    assert resp.status_code == 401


def test_admin_revoga_todas_as_sessoes_de_outro_usuario():
    tenant_id = _criar_tenant()
    _, token_admin = _criar_usuario(tenant_id, 'admin5@meuprecatoriobr.com.br', UserRole.ADMINISTRADOR)
    outro_id, token_outro = _criar_usuario(tenant_id, 'outro2@meuprecatoriobr.com.br', UserRole.VISUALIZADOR)

    client_outro = _client_logado(token_outro)
    assert client_outro.get('/api/me').status_code == 200

    client_admin = _client_logado(token_admin)
    resp = client_admin.post(f'/api/admin/users/{outro_id}/revoke-sessions')
    assert resp.status_code == 200
    assert resp.json()['sessoes_revogadas'] == 1

    resp = client_outro.get('/api/me')
    assert resp.status_code == 401


def test_desativar_usuario_revoga_sessoes_automaticamente():
    tenant_id = _criar_tenant()
    _, token_admin = _criar_usuario(tenant_id, 'admin6@meuprecatoriobr.com.br', UserRole.ADMINISTRADOR)
    outro_id, token_outro = _criar_usuario(tenant_id, 'outro3@meuprecatoriobr.com.br', UserRole.VISUALIZADOR)

    client_admin = _client_logado(token_admin)
    client_admin.patch(f'/api/admin/users/{outro_id}', json={'is_active': False})

    client_outro = _client_logado(token_outro)
    resp = client_outro.get('/api/me')
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def test_criar_usuario_gera_entrada_de_auditoria():
    tenant_id = _criar_tenant()
    _, token_admin = _criar_usuario(tenant_id, 'admin7@meuprecatoriobr.com.br', UserRole.ADMINISTRADOR)
    client = _client_logado(token_admin)
    client.post('/api/admin/users', json={'email': 'auditado@x.com', 'full_name': 'Auditado', 'password': 'senha123456!', 'role': 'pesquisador'})

    resp = client.get('/api/admin/audit-log')
    acoes = [e['action'] for e in resp.json()]
    assert 'criar_usuario' in acoes
    entrada = next(e for e in resp.json() if e['action'] == 'criar_usuario')
    assert entrada['resource_id'] is not None
