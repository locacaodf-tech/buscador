"""Testes do endpoint de diagnóstico — responde 'minha ferramenta está
pronta pra quê' sem jargão técnico."""
import os

os.environ.setdefault('APP_LOGIN_PASSWORD', '')
os.environ.setdefault('INTERNAL_API_TOKEN', '')

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.db import init_db  # noqa: E402

init_db()


def test_diagnostico_reflete_judit_desligada_por_padrao(monkeypatch):
    import app.main as main_module
    monkeypatch.setattr(main_module.settings, 'judit_enabled', False)
    monkeypatch.setattr(main_module.settings, 'judit_api_key', '')

    client = TestClient(app)
    resp = client.get('/api/diagnostico')
    assert resp.status_code == 200
    body = resp.json()
    assert body['judit']['ativo'] is False
    assert body['judit']['proxima_acao'] is not None


def test_diagnostico_reflete_judit_ligada_com_chave(monkeypatch):
    import app.main as main_module
    monkeypatch.setattr(main_module.settings, 'judit_enabled', True)
    monkeypatch.setattr(main_module.settings, 'judit_api_key', 'chave-de-teste')

    client = TestClient(app)
    resp = client.get('/api/diagnostico')
    body = resp.json()
    assert body['judit']['ativo'] is True
    assert body['judit']['proxima_acao'] is None


def test_diagnostico_datajud_sempre_ativo_com_chave_publica():
    client = TestClient(app)
    resp = client.get('/api/diagnostico')
    body = resp.json()
    assert body['datajud']['ativo'] is True


def test_diagnostico_nunca_expoe_chaves_completas(monkeypatch):
    import app.main as main_module
    monkeypatch.setattr(main_module.settings, 'judit_api_key', 'segredo-super-secreto-123')

    client = TestClient(app)
    resp = client.get('/api/diagnostico')
    assert 'segredo-super-secreto-123' not in resp.text


def test_diagnostico_mostra_status_do_stj_upload(tmp_path, monkeypatch):
    from app.services import stj_uploads
    isolado = tmp_path / 'stj_uploads'
    monkeypatch.setattr(stj_uploads, 'UPLOAD_DIR', isolado)
    monkeypatch.setattr(stj_uploads, 'upload_dir', lambda: isolado)

    client = TestClient(app)
    resp = client.get('/api/diagnostico')
    assert resp.json()['stj']['arquivo_carregado'] is False
