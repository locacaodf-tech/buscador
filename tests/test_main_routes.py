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


def test_fluxo_completo_com_senha_configurada(monkeypatch):
    """Com senha configurada: / exige login, /login mostra o form, senha certa
    autentica e mostra o link Sair; senha errada nao autentica."""
    import app.main as main_module
    monkeypatch.setattr(main_module.settings, 'app_login_password', 'segredo123')
    monkeypatch.setattr(main_module, '_login_attempts', {})

    client = TestClient(app)

    resp = client.get('/', follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers['location'] == '/login'

    resp = client.get('/login')
    assert resp.status_code == 200
    assert 'password' in resp.text.lower()

    resp = client.post('/login', data={'password': 'errada'}, follow_redirects=False)
    assert resp.status_code == 401
    assert 'Senha incorreta' in resp.text

    resp = client.post('/login', data={'password': 'segredo123'}, follow_redirects=False)
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
    monkeypatch.setattr(main_module.settings, 'app_login_password', 'segredo123')
    monkeypatch.setattr(main_module, '_login_attempts', {})

    client = TestClient(app)
    for _ in range(main_module.LOGIN_MAX_ATTEMPTS):
        resp = client.post('/login', data={'password': 'errada'})
        assert resp.status_code == 401

    # a tentativa seguinte deve ser bloqueada por rate limit, MESMO com a senha certa
    resp = client.post('/login', data={'password': 'segredo123'})
    assert resp.status_code == 429
    assert 'tentativas' in resp.text.lower()


def test_comparacao_de_senha_e_constant_time(monkeypatch):
    """Garante que a comparação usa hmac.compare_digest, não '!=' direto —
    achado real de segurança da auditoria externa."""
    import inspect
    import app.main as main_module
    source = inspect.getsource(main_module.login_submit)
    assert 'hmac.compare_digest' in source
    assert "password != settings.app_login_password" not in source


def test_alerta_aparece_em_producao_sem_senha(monkeypatch):
    """Achado real da auditoria: produção sem senha fica aberta pra qualquer
    um com o link. Precisa de alerta visível na própria tela."""
    import app.main as main_module
    monkeypatch.setattr(main_module.settings, 'app_env', 'production')
    monkeypatch.setattr(main_module.settings, 'app_login_password', '')

    client = TestClient(app)
    resp = client.get('/')
    assert resp.status_code == 200
    assert 'sem senha' in resp.text.lower()


def test_alerta_nao_aparece_em_producao_com_senha(monkeypatch):
    import app.main as main_module
    monkeypatch.setattr(main_module.settings, 'app_env', 'production')
    monkeypatch.setattr(main_module.settings, 'app_login_password', 'senha-forte-123')
    monkeypatch.setattr(main_module, '_login_attempts', {})

    client = TestClient(app)
    resp = client.get('/login')
    assert 'ferramenta está publicada sem senha' not in resp.text


def test_alerta_nao_aparece_em_ambiente_local_sem_senha(monkeypatch):
    import app.main as main_module
    monkeypatch.setattr(main_module.settings, 'app_env', 'local')
    monkeypatch.setattr(main_module.settings, 'app_login_password', '')

    client = TestClient(app)
    resp = client.get('/')
    assert 'ferramenta está publicada sem senha' not in resp.text
