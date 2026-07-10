"""Testes da persistência e dossiê da diligência (v29): cada chamada a
POST /api/diligencia grava um DiligenciaLog, reabrível e exportável como
dossiê HTML."""
import io
import os

os.environ.setdefault('APP_LOGIN_PASSWORD', '')
os.environ.setdefault('INTERNAL_API_TOKEN', '')

from fastapi.testclient import TestClient

from app.main import app
from app.db import init_db
from app.models import DiligenciaLog
from app.services import stj_uploads

init_db()


def _xlsx_com_credor() -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(['Relação de Precatórios Expedidos - STJ'])
    ws.append([])
    ws.append(['Ordem', 'Classe', 'Sequencial', 'Processo', 'Credor/Beneficiário', 'Valor', 'Previsão'])
    ws.append([1, 'PRC', 15547, '0506671-51.2025.3.00.0000', 'MARIA DA SILVA SOUZA', '1.708.161,78', 'fevereiro/2026'])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _client_com_stj_isolado(tmp_path, monkeypatch):
    isolado = tmp_path / 'stj_uploads'
    monkeypatch.setattr(stj_uploads, 'UPLOAD_DIR', isolado)
    monkeypatch.setattr(stj_uploads, 'upload_dir', lambda: isolado)
    return TestClient(app)


def test_post_diligencia_cria_diligencialog_e_devolve_id():
    client = TestClient(app)
    resp = client.post('/api/diligencia', json={'input': 'teste unico ' + os.urandom(4).hex()})
    assert resp.status_code == 200
    body = resp.json()
    assert 'diligencia_id' in body
    assert isinstance(body['diligencia_id'], int)


def test_get_diligencias_lista_a_mais_recente_primeiro():
    client = TestClient(app)
    r1 = client.post('/api/diligencia', json={'input': 'entrada A ' + os.urandom(4).hex()})
    r2 = client.post('/api/diligencia', json={'input': 'entrada B ' + os.urandom(4).hex()})
    id1, id2 = r1.json()['diligencia_id'], r2.json()['diligencia_id']

    resp = client.get('/api/diligencias', params={'limit': 5})
    assert resp.status_code == 200
    ids = [item['id'] for item in resp.json()]
    assert id2 in ids and id1 in ids
    assert ids.index(id2) < ids.index(id1)  # mais recente primeiro


def test_get_diligencia_por_id_retorna_todo_o_detalhe():
    client = TestClient(app)
    entrada = 'detalhe completo ' + os.urandom(4).hex()
    created = client.post('/api/diligencia', json={'input': entrada}).json()

    resp = client.get(f"/api/diligencias/{created['diligencia_id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body['input_original'] == entrada
    assert 'raw_avancado' in body
    assert 'pendencias' in body


def test_get_diligencia_inexistente_devolve_404():
    client = TestClient(app)
    resp = client.get('/api/diligencias/999999')
    assert resp.status_code == 404


def test_dossie_retorna_html_com_dados_da_diligencia():
    client = TestClient(app)
    entrada = 'dossie html ' + os.urandom(4).hex()
    created = client.post('/api/diligencia', json={'input': entrada}).json()

    resp = client.get(f"/api/diligencias/{created['diligencia_id']}/dossie")
    assert resp.status_code == 200
    assert 'text/html' in resp.headers['content-type']
    assert entrada in resp.text
    assert 'confirmação oficial' in resp.text.lower()


def test_dossie_de_diligencia_inexistente_devolve_404():
    client = TestClient(app)
    resp = client.get('/api/diligencias/999999/dossie')
    assert resp.status_code == 404


def test_cpf_sem_provider_salva_orientacao_no_log(tmp_path, monkeypatch):
    from app.services import diligencia_engine

    client = TestClient(app)
    resp = client.post('/api/diligencia', json={'input': '721.377.971-00'})
    body = resp.json()
    log_resp = client.get(f"/api/diligencias/{body['diligencia_id']}")
    log = log_resp.json()
    assert log['tipo_identificado'] == 'cpf'
    assert 'provider comercial' in log['proxima_acao_recomendada'].lower()


def test_stj_com_xlsx_salva_resultado_confirmado(tmp_path, monkeypatch):
    client = _client_com_stj_isolado(tmp_path, monkeypatch)
    client.post('/api/stj-precatorios/upload-xlsx', files={'file': ('teste.xlsx', _xlsx_com_credor(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})

    resp = client.post('/api/diligencia', json={'input': '15547'})
    body = resp.json()
    log = client.get(f"/api/diligencias/{body['diligencia_id']}").json()
    assert len(log['resultados_confirmados']) == 1
    assert log['resultados_confirmados'][0]['sequencial'] == '15547'


def test_cnj_com_datajud_mockado_salva_resultado(monkeypatch):
    async def fake_search(self, search_type, search_key, **kwargs):
        return [{'numero_processo': search_key, 'tribunal': 'TRF1', 'classe': 'Teste', 'precatorio_score': 0}]

    monkeypatch.setattr('app.connectors.datajud.DataJudConnector.search', fake_search)
    client = TestClient(app)
    resp = client.post('/api/diligencia', json={'input': '0032681-47.2017.4.01.3400'})
    body = resp.json()
    log = client.get(f"/api/diligencias/{body['diligencia_id']}").json()
    assert log['tipo_identificado'] == 'cnj'


def test_pendencias_sao_salvas_no_log(tmp_path, monkeypatch):
    isolado = tmp_path / 'stj_uploads'
    monkeypatch.setattr(stj_uploads, 'UPLOAD_DIR', isolado)
    monkeypatch.setattr(stj_uploads, 'upload_dir', lambda: isolado)

    client = TestClient(app)
    resp = client.post('/api/diligencia', json={'input': '15547'})  # sem XLSX carregado -> pendencia
    body = resp.json()
    log = client.get(f"/api/diligencias/{body['diligencia_id']}").json()
    assert log['pendencias']
    assert any('xlsx' in p.lower() for p in log['pendencias'])


def test_proxima_acao_e_sempre_salva():
    client = TestClient(app)
    resp = client.post('/api/diligencia', json={'input': 'qualquer coisa ' + os.urandom(4).hex()})
    body = resp.json()
    log = client.get(f"/api/diligencias/{body['diligencia_id']}").json()
    assert log['proxima_acao_recomendada']
