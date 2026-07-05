"""Testes do hotfix (correção dos erros reais dos prints de tela):
- STJ, plano de precatório e solicitação de certidão agora também salvam
  DiligenciaLog (antes só a busca livre/CNJ salvava).
- Plano de precatório reflete o estado real do upload do STJ, não o status
  estático do registry.
- Inferência de tribunal cobre também Justiça Estadual, não só Federal.
"""
import io
import os

os.environ.setdefault('APP_LOGIN_PASSWORD', '')
os.environ.setdefault('INTERNAL_API_TOKEN', '')

from fastapi.testclient import TestClient

from app.main import app
from app.db import init_db
from app.services import stj_uploads
from app.utils.cnj import infer_tribunal_from_cnj

init_db()


def _xlsx_simples() -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(['Relação de Precatórios Expedidos - STJ'])
    ws.append([])
    ws.append(['Ordem', 'Classe', 'Sequencial', 'Processo', 'Valor', 'Previsão'])
    ws.append([1, 'PRC', 15547, '0506671-51.2025.3.00.0000', '1.708.161,78', 'fevereiro/2026'])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _client_com_stj_isolado(tmp_path, monkeypatch):
    isolado = tmp_path / 'stj_uploads'
    monkeypatch.setattr(stj_uploads, 'UPLOAD_DIR', isolado)
    monkeypatch.setattr(stj_uploads, 'upload_dir', lambda: isolado)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Inferência de tribunal estadual (achado real do print: CNJ 0875356-48.2024.8.15.2001)
# ---------------------------------------------------------------------------

def test_infere_tribunal_estadual_a_partir_do_cnj():
    assert infer_tribunal_from_cnj('0875356-48.2024.8.15.2001') == 'TJPB'
    assert infer_tribunal_from_cnj('0000000-00.2020.8.26.0100') == 'TJSP'
    assert infer_tribunal_from_cnj('0000000-00.2020.8.19.0001') == 'TJRJ'


def test_infere_tribunal_federal_continua_funcionando():
    assert infer_tribunal_from_cnj('0032681-47.2017.4.01.3400') == 'TRF1'


def test_segmento_nao_mapeado_devolve_none():
    assert infer_tribunal_from_cnj('0000000-00.2020.5.10.0001') is None  # trabalhista, nao coberto


# ---------------------------------------------------------------------------
# STJ, precatório e certidão agora salvam DiligenciaLog
# ---------------------------------------------------------------------------

def test_stj_search_salva_diligencia_com_xlsx_carregado(tmp_path, monkeypatch):
    client = _client_com_stj_isolado(tmp_path, monkeypatch)
    client.post('/api/stj-precatorios/upload-xlsx', files={'file': ('t.xlsx', _xlsx_simples(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})

    resp = client.post('/api/stj-precatorios/search', json={'search_type': 'sequencial', 'search_key': '15547'})
    body = resp.json()
    assert 'diligencia_id' in body
    log = client.get(f"/api/diligencias/{body['diligencia_id']}").json()
    assert log['tipo_identificado'] == 'stj_sequencial'
    assert len(log['resultados_confirmados']) == 1


def test_stj_search_sem_xlsx_salva_diligencia_com_pendencia(tmp_path, monkeypatch):
    client = _client_com_stj_isolado(tmp_path, monkeypatch)
    resp = client.post('/api/stj-precatorios/search', json={'search_type': 'sequencial', 'search_key': '99999'})
    body = resp.json()
    assert 'diligencia_id' in body
    log = client.get(f"/api/diligencias/{body['diligencia_id']}").json()
    assert log['pendencias']
    assert any('xlsx' in p.lower() for p in log['pendencias'])


def test_plano_precatorio_salva_diligencia():
    client = TestClient(app)
    resp = client.post('/api/official-precatorio/plan', json={'search_type': 'precatorio_number', 'search_key': '55555'})
    body = resp.json()
    assert 'diligencia_id' in body
    log = client.get(f"/api/diligencias/{body['diligencia_id']}").json()
    assert log['objetivo'] == 'precatorio'
    assert log['proxima_acao_recomendada']


def test_certidao_request_salva_diligencia_com_documento_mascarado():
    client = TestClient(app)
    resp = client.post('/api/certificates/request', json={'source_id': 'tjpe_certidoes', 'certificate_type': 'civel', 'document': '25683919000158'})
    body = resp.json()
    assert 'diligencia_id' in body
    log = client.get(f"/api/diligencias/{body['diligencia_id']}").json()
    assert log['input_original'].startswith('25.')  # mascarado (CNPJ: 2 primeiros digitos visiveis)
    assert '25683919000158' not in log['input_original']  # nunca cru, sem mascara
    assert 'captcha' in log['resumo_humano'].lower()


# ---------------------------------------------------------------------------
# Plano de precatório reflete o estado real do upload do STJ (achado do print)
# ---------------------------------------------------------------------------

def test_diagnostico_stj_reflete_upload_real(tmp_path, monkeypatch):
    client = _client_com_stj_isolado(tmp_path, monkeypatch)
    resp = client.get('/api/diagnostico')
    assert resp.json()['stj']['arquivo_carregado'] is False

    client.post('/api/stj-precatorios/upload-xlsx', files={'file': ('t.xlsx', _xlsx_simples(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    resp2 = client.get('/api/diagnostico')
    assert resp2.json()['stj']['arquivo_carregado'] is True
