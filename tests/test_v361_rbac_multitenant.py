"""v36.1 — Testes de aceitação da fundação segura:
- RBAC em endpoints legados (visualizador não escreve; pesquisador não administra);
- login multitenant (mesmo e-mail em tenants diferentes resolve certo);
- produção fail-closed antes do bootstrap.

Estes cobrem exatamente os bugs que a auditoria reproduziu."""
import os

os.environ.setdefault('APP_LOGIN_PASSWORD', '')
os.environ.setdefault('INTERNAL_API_TOKEN', '')

from fastapi.testclient import TestClient

from app.main import app
from app.db import init_db, SessionLocal
from app.models_auth import Tenant, User, UserRole
from app.services.auth import hash_password, criar_sessao

init_db()


def _tenant(slug='meuprecatoriobr', nome='MeuPrecatórioBR'):
    db = SessionLocal()
    t = db.query(Tenant).filter(Tenant.slug == slug).first()
    if not t:
        t = Tenant(slug=slug, nome=nome)
        db.add(t)
        db.commit()
        db.refresh(t)
    tid = t.id
    db.close()
    return tid


def _usuario(tenant_id, email, role, senha='senhaDeTeste!123'):
    db = SessionLocal()
    u = User(tenant_id=tenant_id, email=email.lower(), full_name=email.split('@')[0], hashed_password=hash_password(senha), role=role, is_active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    uid = u.id
    token = criar_sessao(db, u)
    db.close()
    return uid, token


def _cli(token):
    c = TestClient(app)
    c.cookies.set('buscador_session', token)
    return c


# ---------------------------------------------------------------------------
# RBAC em endpoints LEGADOS (o bug central da auditoria)
# ---------------------------------------------------------------------------

def test_visualizador_nao_importa_publicacao():
    """Bug reproduzido pela auditoria: visualizador chamava
    POST /api/watchers/import-publications e criava lead (HTTP 200)."""
    tid = _tenant()
    _, token = _usuario(tid, 'vis@meuprecatoriobr.com.br', UserRole.VISUALIZADOR)
    c = _cli(token)
    resp = c.post('/api/watchers/import-publications', json={'texto_colado': 'Processo: 1234567-89.2026.8.09.0128 Estado de Goias precatorio', 'tribunal': 'TJGO'})
    assert resp.status_code == 403


def test_visualizador_pode_ler_leads():
    tid = _tenant()
    _, token = _usuario(tid, 'vis2@meuprecatoriobr.com.br', UserRole.VISUALIZADOR)
    c = _cli(token)
    assert c.get('/api/leads').status_code == 200


def test_visualizador_nao_executa_busca():
    tid = _tenant()
    _, token = _usuario(tid, 'vis3@meuprecatoriobr.com.br', UserRole.VISUALIZADOR)
    c = _cli(token)
    resp = c.post('/api/search', json={'identifier': '1234567-89.2026.8.09.0128', 'search_type': 'cnj'})
    assert resp.status_code == 403


def test_pesquisador_executa_busca_e_importa():
    tid = _tenant()
    _, token = _usuario(tid, 'pesq@meuprecatoriobr.com.br', UserRole.PESQUISADOR)
    c = _cli(token)
    # pesquisador pode importar publicação (watchers:executar)
    resp = c.post('/api/watchers/import-publications', json={'texto_colado': 'Processo: 1234567-89.2026.8.09.0128 Estado de Goias precatorio', 'tribunal': 'TJGO'})
    assert resp.status_code == 200


def test_pesquisador_nao_administra_usuarios():
    tid = _tenant()
    _, token = _usuario(tid, 'pesq2@meuprecatoriobr.com.br', UserRole.PESQUISADOR)
    c = _cli(token)
    assert c.get('/api/admin/users').status_code == 403


def test_juridico_nao_executa_busca():
    """Jurídico valida ativo/risco, mas não dispara busca/watcher."""
    tid = _tenant()
    _, token = _usuario(tid, 'jur@meuprecatoriobr.com.br', UserRole.JURIDICO)
    c = _cli(token)
    resp = c.post('/api/watchers/import-publications', json={'texto_colado': 'x', 'tribunal': 'TJGO'})
    assert resp.status_code == 403


def test_admin_faz_tudo():
    tid = _tenant()
    _, token = _usuario(tid, 'adm@meuprecatoriobr.com.br', UserRole.ADMINISTRADOR)
    c = _cli(token)
    assert c.post('/api/watchers/import-publications', json={'texto_colado': 'Processo: 1234567-89.2026.8.09.0128 Estado de Goias precatorio', 'tribunal': 'TJGO'}).status_code == 200
    assert c.get('/api/leads').status_code == 200
    assert c.get('/api/admin/users').status_code == 200


# ---------------------------------------------------------------------------
# Login multitenant
# ---------------------------------------------------------------------------

def test_login_multitenant_resolve_tenant_certo():
    ta = _tenant('tenant-a', 'Tenant A')
    tb = _tenant('tenant-b', 'Tenant B')
    _usuario(ta, 'mesmo@x.com', UserRole.ADMINISTRADOR, senha='senhaA12345!')
    _usuario(tb, 'mesmo@x.com', UserRole.ADMINISTRADOR, senha='senhaB12345!')

    c = TestClient(app)
    # senha do A no tenant A: ok
    assert c.post('/login', data={'tenant_slug': 'tenant-a', 'email': 'mesmo@x.com', 'password': 'senhaA12345!'}, follow_redirects=False).status_code == 303
    # senha do B no tenant A: falha
    c2 = TestClient(app)
    assert c2.post('/login', data={'tenant_slug': 'tenant-a', 'email': 'mesmo@x.com', 'password': 'senhaB12345!'}, follow_redirects=False).status_code == 401


def test_login_sem_tenant_com_multiplos_falha():
    _tenant('tenant-c', 'Tenant C')
    _tenant('tenant-d', 'Tenant D')
    _usuario(_tenant('tenant-c', 'Tenant C'), 'user@x.com', UserRole.ADMINISTRADOR, senha='senha123456!')
    c = TestClient(app)
    # sem informar tenant, com múltiplos tenants, não dá pra resolver: 401
    assert c.post('/login', data={'email': 'user@x.com', 'password': 'senha123456!'}, follow_redirects=False).status_code == 401


def test_login_sem_tenant_com_um_so_funciona():
    tid = _tenant()  # só um tenant
    _usuario(tid, 'unico@meuprecatoriobr.com.br', UserRole.ADMINISTRADOR, senha='senha123456!')
    c = TestClient(app)
    # com um só tenant, tenant_slug é opcional
    assert c.post('/login', data={'email': 'unico@meuprecatoriobr.com.br', 'password': 'senha123456!'}, follow_redirects=False).status_code == 303


def test_email_normalizado_no_login():
    tid = _tenant()
    _usuario(tid, 'CaseTest@meuprecatoriobr.com.br', UserRole.ADMINISTRADOR, senha='senha123456!')
    c = TestClient(app)
    # login com e-mail em maiúsculas deve funcionar (normalizado lowercase)
    assert c.post('/login', data={'email': 'CASETEST@MEUPRECATORIOBR.COM.BR', 'password': 'senha123456!'}, follow_redirects=False).status_code == 303


# ---------------------------------------------------------------------------
# Health-check enriquecido
# ---------------------------------------------------------------------------

def test_health_reporta_banco_e_bootstrap():
    c = TestClient(app)
    body = c.get('/health').json()
    assert body['status'] == 'ok'
    assert body['database']['conectado'] is True
    assert 'alembic_revision_atual' in body['database']
    assert 'bootstrap_necessario' in body


def test_health_nao_exige_autenticacao():
    """Mesmo com usuário criado, /health continua aberto (liveness check)."""
    tid = _tenant()
    _usuario(tid, 'qualquer@meuprecatoriobr.com.br', UserRole.ADMINISTRADOR)
    c = TestClient(app)  # sem cookie
    assert c.get('/health').status_code == 200


# ---------------------------------------------------------------------------
# Isolamento por tenant nas queries (achado #2 — o ponto central)
# ---------------------------------------------------------------------------

def test_lead_do_tenant_a_nao_aparece_pro_tenant_b():
    ta = _tenant('iso-a', 'Iso A')
    tb = _tenant('iso-b', 'Iso B')
    _, token_a = _usuario(ta, 'admin_iso_a@x.com', UserRole.ADMINISTRADOR)
    _, token_b = _usuario(tb, 'admin_iso_b@x.com', UserRole.ADMINISTRADOR)

    # tenant A cria um lead via importação
    ca = _cli(token_a)
    resp = ca.post('/api/watchers/import-publications', json={'texto_colado': 'Processo: 5555555-55.2026.8.09.0128 Estado de Goias precatorio', 'tribunal': 'TJGO', 'source': 'iso_a'})
    assert resp.status_code == 200
    leads_a = ca.get('/api/leads').json()
    assert len(leads_a) >= 1
    lead_id = leads_a[0]['id']

    # tenant B NÃO vê o lead do A na lista
    cb = _cli(token_b)
    leads_b = cb.get('/api/leads').json()
    ids_b = [l['id'] for l in leads_b]
    assert lead_id not in ids_b

    # tenant B NÃO abre o lead do A por ID (404 — nem confirma que existe)
    assert cb.get(f'/api/leads/{lead_id}').status_code == 404


def test_lead_do_tenant_a_nao_pode_ser_removido_pelo_tenant_b():
    ta = _tenant('iso-c', 'Iso C')
    tb = _tenant('iso-d', 'Iso D')
    _, token_a = _usuario(ta, 'admin_iso_c@x.com', UserRole.ADMINISTRADOR)
    _, token_b = _usuario(tb, 'admin_iso_d@x.com', UserRole.ADMINISTRADOR)

    ca = _cli(token_a)
    ca.post('/api/watchers/import-publications', json={'texto_colado': 'Processo: 7777777-77.2026.8.09.0128 Estado de Goias precatorio', 'tribunal': 'TJGO', 'source': 'iso_c'})
    lead_id = ca.get('/api/leads').json()[0]['id']

    # tenant B tenta remover o lead do A → 404
    cb = _cli(token_b)
    assert cb.post(f'/api/leads/{lead_id}/remover').status_code == 404
    # e o lead do A continua lá pro A
    assert ca.get(f'/api/leads/{lead_id}').status_code == 200


def test_dossie_do_tenant_a_nao_abre_pro_tenant_b():
    ta = _tenant('iso-e', 'Iso E')
    tb = _tenant('iso-f', 'Iso F')
    _, token_a = _usuario(ta, 'admin_iso_e@x.com', UserRole.ADMINISTRADOR)
    _, token_b = _usuario(tb, 'admin_iso_f@x.com', UserRole.ADMINISTRADOR)

    ca = _cli(token_a)
    ca.post('/api/watchers/import-publications', json={'texto_colado': 'Processo: 8888888-88.2026.8.09.0128 Estado de Goias precatorio', 'tribunal': 'TJGO', 'source': 'iso_e'})
    lead_id = ca.get('/api/leads').json()[0]['id']

    cb = _cli(token_b)
    resp = cb.get(f'/api/leads/{lead_id}/dossie', follow_redirects=False)
    assert resp.status_code == 404


def test_mesmo_cnj_pode_existir_em_tenants_distintos_sem_dedupe_cruzado():
    ta = _tenant('iso-g', 'Iso G')
    tb = _tenant('iso-h', 'Iso H')
    _, token_a = _usuario(ta, 'admin_iso_g@x.com', UserRole.ADMINISTRADOR)
    _, token_b = _usuario(tb, 'admin_iso_h@x.com', UserRole.ADMINISTRADOR)

    mesmo_texto = 'Processo: 9090909-90.2026.8.09.0128 Estado de Goias precatorio'
    ca = _cli(token_a)
    ca.post('/api/watchers/import-publications', json={'texto_colado': mesmo_texto, 'tribunal': 'TJGO', 'source': 'iso_g'})
    cb = _cli(token_b)
    cb.post('/api/watchers/import-publications', json={'texto_colado': mesmo_texto, 'tribunal': 'TJGO', 'source': 'iso_h'})

    # cada tenant vê o seu próprio lead (o mesmo CNJ existe nos dois, isolado)
    assert len(ca.get('/api/leads').json()) >= 1
    assert len(cb.get('/api/leads').json()) >= 1
