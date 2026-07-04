"""Testes do registro manual de evidência: salvar com texto, salvar com
arquivo, rejeitar extensão não permitida, rejeitar registro vazio, listar."""
import io
import os

os.environ.setdefault('APP_LOGIN_PASSWORD', '')
os.environ.setdefault('INTERNAL_API_TOKEN', '')

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.db import init_db  # noqa: E402
from app.services import manual_evidence  # noqa: E402

init_db()


def _client(tmp_path, monkeypatch):
    isolado = tmp_path / 'evidencias_manuais'
    monkeypatch.setattr(manual_evidence, 'EVIDENCE_DIR', isolado)
    monkeypatch.setattr(manual_evidence, 'evidence_dir', lambda: isolado)
    return TestClient(app)


def test_salvar_evidencia_so_com_texto(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    resp = client.post('/api/evidencias', data={'fonte': 'TRF1 portal manual', 'referencia': '0032681-47.2017.4.01.3400', 'texto': 'Encontrei o processo, valor R$ 150.000,00'})
    assert resp.status_code == 200
    body = resp.json()
    assert body['status'] == 'salvo'
    assert body['tem_texto'] is True
    assert body['arquivo_nome'] is None


def test_salvar_evidencia_com_arquivo_pdf(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    arquivo = io.BytesIO(b'%PDF-1.4 conteudo de teste')
    resp = client.post(
        '/api/evidencias',
        data={'fonte': 'TRF1 print manual', 'referencia': '123'},
        files={'arquivo': ('print_processo.pdf', arquivo, 'application/pdf')},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body['arquivo_nome'] == 'print_processo.pdf'
    saved = list((tmp_path / 'evidencias_manuais').glob('*.pdf'))
    assert len(saved) == 1


def test_rejeita_extensao_nao_permitida(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    arquivo = io.BytesIO(b'conteudo qualquer')
    resp = client.post(
        '/api/evidencias',
        data={'fonte': 'teste'},
        files={'arquivo': ('script.exe', arquivo, 'application/octet-stream')},
    )
    assert resp.status_code == 400
    assert 'não permitida' in resp.json()['detail']


def test_rejeita_registro_vazio_sem_texto_e_sem_arquivo(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    resp = client.post('/api/evidencias', data={'fonte': 'teste'})
    assert resp.status_code == 400


def test_listar_evidencias_filtra_por_referencia(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post('/api/evidencias', data={'fonte': 'A', 'referencia': 'CNJ-1', 'texto': 'nota 1'})
    client.post('/api/evidencias', data={'fonte': 'B', 'referencia': 'CNJ-2', 'texto': 'nota 2'})

    resp = client.get('/api/evidencias', params={'referencia': 'CNJ-1'})
    assert resp.status_code == 200
    resultado = resp.json()
    assert len(resultado) == 1
    assert resultado[0]['fonte'] == 'A'


def test_sanitiza_nome_de_arquivo_perigoso(tmp_path, monkeypatch):
    isolado = tmp_path / 'evidencias_manuais'
    monkeypatch.setattr(manual_evidence, 'EVIDENCE_DIR', isolado)
    monkeypatch.setattr(manual_evidence, 'evidence_dir', lambda: isolado)
    nome, caminho = manual_evidence.save_evidence_file('../../etc/passwd.pdf', b'conteudo')
    assert '..' not in caminho
    assert (tmp_path / 'evidencias_manuais').resolve() in __import__('pathlib').Path(caminho).resolve().parents
