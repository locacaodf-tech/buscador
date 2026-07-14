"""Testes das rotas raiz e de login — nunca tinham cobertura dedicada antes.
Existir esse arquivo é o que garante que uma futura migração de FastAPI/Starlette
(ou qualquer mudança na assinatura do TemplateResponse) quebre a suíte
imediatamente, em vez de só aparecer em produção."""
import os

os.environ.setdefault('APP_LOGIN_PASSWORD', '')
os.environ.setdefault('INTERNAL_API_TOKEN', '')

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.db import init_db  # noqa: E402

init_db()


def test_raiz_sem_senha_configurada_responde_200():
    """Sem APP_LOGIN_PASSWORD, / deve renderizar direto, sem exigir login."""
    client = TestClient(app)
    resp = client.get('/', follow_redirects=False)
    assert resp.status_code == 200
    assert 'Buscador Interno de Processos' in resp.text
    assert 'Sair' not in resp.text  # login_enabled=False não deve mostrar o link


def test_login_get_redireciona_para_raiz_quando_login_desabilitado():
    client = TestClient(app)
    resp = client.get('/login', follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers['location'] == '/'


def _criar_usuario_teste(email='teste@meuprecatoriobr.com.br', senha='segredo123456!', role=None):
    from app.db import SessionLocal
    from app.models_auth import Tenant, User, UserRole
    from app.services.auth import hash_password
    db = SessionLocal()
    tenant = db.query(Tenant).filter(Tenant.slug == 'meuprecatoriobr').first()
    if not tenant:
        tenant = Tenant(slug='meuprecatoriobr', nome='MeuPrecatórioBR')
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(tenant_id=tenant.id, email=email, full_name='Usuário de Teste', hashed_password=hash_password(senha), role=role or UserRole.ADMINISTRADOR, is_active=True)
        db.add(user)
        db.commit()
    db.close()
    return email, senha


def test_fluxo_completo_com_usuario_configurado(monkeypatch):
    """Com usuário configurado: / exige login, /login mostra o form, senha certa
    autentica e mostra o link Sair; senha errada nao autentica."""
    import app.main as main_module
    monkeypatch.setattr(main_module, '_login_attempts', {})
    email, senha = _criar_usuario_teste('fluxo@meuprecatoriobr.com.br')

    client = TestClient(app)

    resp = client.get('/', follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers['location'] == '/login'

    resp = client.get('/login')
    assert resp.status_code == 200
    assert 'password' in resp.text.lower()
    assert 'email' in resp.text.lower()

    resp = client.post('/login', data={'email': email, 'password': 'errada'}, follow_redirects=False)
    assert resp.status_code == 401
    assert 'incorretos' in resp.text.lower()

    resp = client.post('/login', data={'email': email, 'password': senha}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers['location'] == '/'
    cookie = resp.cookies.get('buscador_session')
    assert cookie

    client.cookies.set('buscador_session', cookie)
    resp = client.get('/')
    assert resp.status_code == 200
    assert 'Sair' in resp.text


def test_rate_limit_bloqueia_apos_muitas_tentativas(monkeypatch):
    import app.main as main_module
    monkeypatch.setattr(main_module, '_login_attempts', {})
    email, senha = _criar_usuario_teste('ratelimit@meuprecatoriobr.com.br')

    client = TestClient(app)
    for _ in range(main_module.LOGIN_MAX_ATTEMPTS):
        resp = client.post('/login', data={'email': email, 'password': 'errada'})
        assert resp.status_code == 401

    # a tentativa seguinte deve ser bloqueada por rate limit, MESMO com a senha certa
    resp = client.post('/login', data={'email': email, 'password': senha})
    assert resp.status_code == 429
    assert 'tentativas' in resp.text.lower()


def test_verificacao_de_senha_usa_hash_bcrypt():
    """Garante que a comparação usa passlib/bcrypt (hash + verify,
    constant-time por natureza do algoritmo), não comparação direta de
    string — achado real de segurança da auditoria externa, agora
    resolvido de raiz com hash de senha de verdade (nunca senha em claro
    no banco)."""
    import inspect
    import app.main as main_module
    source = inspect.getsource(main_module.login_submit)
    assert 'verify_password' in source
    assert "password != " not in source
    assert "password == " not in source

    from app.models_auth import User
    from app.db import SessionLocal
    _criar_usuario_teste('hashcheck@meuprecatoriobr.com.br', 'senhaDeTeste!789')
    db = SessionLocal()
    user = db.query(User).filter(User.email == 'hashcheck@meuprecatoriobr.com.br').first()
    assert user.hashed_password != 'senhaDeTeste!789'  # nunca em claro
    assert user.hashed_password.startswith('$2b$')  # hash bcrypt de verdade
    db.close()


def test_alerta_aparece_em_producao_sem_senha(monkeypatch):
    """Achado real da auditoria: produção sem nenhum usuário criado ainda
    (bootstrap não rodado) fica aberta pra qualquer um com o link. Precisa
    de alerta visível na própria tela."""
    import app.main as main_module
    monkeypatch.setattr(main_module.settings, 'app_env', 'production')

    client = TestClient(app)
    resp = client.get('/')
    assert resp.status_code == 200
    assert 'sem senha' in resp.text.lower()


def test_alerta_nao_aparece_em_producao_com_usuario_configurado(monkeypatch):
    import app.main as main_module
    monkeypatch.setattr(main_module.settings, 'app_env', 'production')
    monkeypatch.setattr(main_module, '_login_attempts', {})
    _criar_usuario_teste('semalerta@meuprecatoriobr.com.br')

    client = TestClient(app)
    resp = client.get('/login')
    assert 'ferramenta está publicada sem senha' not in resp.text


def test_alerta_nao_aparece_em_ambiente_local_sem_senha(monkeypatch):
    import app.main as main_module
    monkeypatch.setattr(main_module.settings, 'app_env', 'local')

    client = TestClient(app)
    resp = client.get('/')
    assert 'ferramenta está publicada sem senha' not in resp.text
