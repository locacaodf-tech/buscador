"""Testes da v30.1 — bots maturados. Cobre exatamente a lista pedida: status
correto do BotJob (pendência nunca vira completed), /api/diligencia com
run_bots, dossiê do job, evidence_id salvo por bot, PortalBot sem alvo não
conta como executado."""
import io
import os

import pytest

os.environ.setdefault('APP_LOGIN_PASSWORD', '')
os.environ.setdefault('INTERNAL_API_TOKEN', '')

from fastapi.testclient import TestClient

from app.main import app
from app.db import init_db
from app.services import stj_uploads
from app.bots.runner import calcular_status_job

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


# ---------------------------------------------------------------------------
# Regra de agregação de status (unitário, direto na função)
# ---------------------------------------------------------------------------

def test_calcular_status_todos_concluidos_e_completed():
    assert calcular_status_job([{'status': 'concluido'}, {'status': 'concluido'}]) == 'completed'


def test_calcular_status_qualquer_pendente_e_partial():
    assert calcular_status_job([{'status': 'concluido'}, {'status': 'pendente'}]) == 'partial'


def test_calcular_status_qualquer_waiting_user_prevalece():
    assert calcular_status_job([{'status': 'concluido'}, {'status': 'waiting_user'}, {'status': 'pendente'}]) == 'waiting_user'


def test_calcular_status_tudo_falhou_e_failed():
    assert calcular_status_job([{'status': 'falhou'}, {'status': 'falhou'}]) == 'failed'


def test_calcular_status_falha_parcial_e_partial():
    assert calcular_status_job([{'status': 'concluido'}, {'status': 'falhou'}]) == 'partial'


def test_calcular_status_sem_passos_e_completed():
    assert calcular_status_job([]) == 'completed'


# ---------------------------------------------------------------------------
# A) input 15547 sem XLSX: StjBot = pendente, BotJob = partial
# ---------------------------------------------------------------------------

def test_sequencial_sem_xlsx_stjbot_pendente_e_job_partial(tmp_path, monkeypatch):
    isolado = tmp_path / 'stj_uploads'
    monkeypatch.setattr(stj_uploads, 'UPLOAD_DIR', isolado)
    monkeypatch.setattr(stj_uploads, 'upload_dir', lambda: isolado)

    client = TestClient(app)
    resp = client.post('/api/bots/run', json={'input': '15547'})
    body = resp.json()
    assert body['status'] == 'partial'
    stj_step = next(b for b in body['bots_executados'] if b['bot_id'] == 'stj_bot')
    assert stj_step['status'] == 'pendente'

    job = client.get(f"/api/bots/jobs/{body['job_id']}").json()
    assert job['status'] == 'partial'


# ---------------------------------------------------------------------------
# B) input PRC 123456 sem XLSX/tribunal/ano: StjBot=pendente,
# PrecatorioBot=plano gerado, BotJob=partial
# ---------------------------------------------------------------------------

def test_precatorio_sem_xlsx_tribunal_ano_gera_job_partial(tmp_path, monkeypatch):
    isolado = tmp_path / 'stj_uploads'
    monkeypatch.setattr(stj_uploads, 'UPLOAD_DIR', isolado)
    monkeypatch.setattr(stj_uploads, 'upload_dir', lambda: isolado)

    client = TestClient(app)
    resp = client.post('/api/bots/run', json={'input': 'PRC 123456', 'objetivo': 'precatorio'})
    body = resp.json()
    assert body['status'] == 'partial'
    stj_step = next(b for b in body['bots_executados'] if b['bot_id'] == 'stj_bot')
    precatorio_step = next(b for b in body['bots_executados'] if b['bot_id'] == 'precatorio_bot')
    assert stj_step['status'] == 'pendente'
    assert precatorio_step['status'] == 'concluido'  # gerou o plano, mesmo com pendências dentro dele


# ---------------------------------------------------------------------------
# STJ com XLSX carregado: tudo concluído, job completed
# ---------------------------------------------------------------------------

def test_stj_com_xlsx_job_fica_completed(tmp_path, monkeypatch):
    isolado = tmp_path / 'stj_uploads'
    monkeypatch.setattr(stj_uploads, 'UPLOAD_DIR', isolado)
    monkeypatch.setattr(stj_uploads, 'upload_dir', lambda: isolado)

    client = TestClient(app)
    client.post('/api/stj-precatorios/upload-xlsx', files={'file': ('teste.xlsx', _xlsx_com_credor(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    resp = client.post('/api/bots/run', json={'input': '15547'})
    body = resp.json()
    assert body['status'] == 'completed'


# ---------------------------------------------------------------------------
# /api/diligencia com run_bots
# ---------------------------------------------------------------------------

def test_diligencia_com_run_bots_true_devolve_job_id():
    client = TestClient(app)
    resp = client.post('/api/diligencia', json={'input': '721.377.971-00', 'run_bots': True})
    body = resp.json()
    assert 'diligencia_id' in body
    assert 'job_id' in body
    assert 'bots_resumo' in body


def test_diligencia_sem_run_bots_mantem_comportamento_antigo():
    client = TestClient(app)
    resp = client.post('/api/diligencia', json={'input': '721.377.971-00'})
    body = resp.json()
    assert 'diligencia_id' in body
    assert 'job_id' not in body
    assert 'bots_resumo' not in body


# ---------------------------------------------------------------------------
# Dossiê do job
# ---------------------------------------------------------------------------

def test_dossie_do_job_retorna_html():
    client = TestClient(app)
    job_id = client.post('/api/bots/run', json={'input': '721.377.971-00'}).json()['job_id']
    resp = client.get(f'/api/bots/jobs/{job_id}/dossie')
    assert resp.status_code == 200
    assert 'text/html' in resp.headers['content-type']
    assert '721.377.971-00' in resp.text


def test_dossie_de_job_inexistente_devolve_404():
    client = TestClient(app)
    assert client.get('/api/bots/jobs/999999/dossie').status_code == 404


# ---------------------------------------------------------------------------
# evidence_id salvo por bot
# ---------------------------------------------------------------------------

def test_datajud_bot_salva_evidence_id(monkeypatch):
    async def fake_search(self, search_type, search_key, **kwargs):
        return [{'numero_processo': search_key, 'tribunal': 'TRF1', 'classe': 'Teste', 'precatorio_score': 0}]

    monkeypatch.setattr('app.connectors.datajud.DataJudConnector.search', fake_search)
    client = TestClient(app)
    resp = client.post('/api/bots/run', json={'input': '0032681-47.2017.4.01.3400'})
    job = client.get(f"/api/bots/jobs/{resp.json()['job_id']}").json()
    datajud_step = next(s for s in job['steps'] if s['bot_name'] == 'datajud_bot')
    assert datajud_step['evidence_id'] is not None


def test_stj_bot_salva_evidence_id(tmp_path, monkeypatch):
    isolado = tmp_path / 'stj_uploads'
    monkeypatch.setattr(stj_uploads, 'UPLOAD_DIR', isolado)
    monkeypatch.setattr(stj_uploads, 'upload_dir', lambda: isolado)

    client = TestClient(app)
    resp = client.post('/api/bots/run', json={'input': '15547'})
    job = client.get(f"/api/bots/jobs/{resp.json()['job_id']}").json()
    stj_step = next(s for s in job['steps'] if s['bot_name'] == 'stj_bot')
    assert stj_step['evidence_id'] is not None  # mesmo pendente, a pendência vira evidência


def test_certidao_bot_salva_evidence_id():
    client = TestClient(app)
    resp = client.post('/api/bots/run', json={'input': '25683919000158', 'objetivo': 'certidao'})
    job = client.get(f"/api/bots/jobs/{resp.json()['job_id']}").json()
    cert_step = next(s for s in job['steps'] if s['bot_name'] == 'certidao_bot')
    assert cert_step['evidence_id'] is not None


# ---------------------------------------------------------------------------
# PortalBot sem alvo não conta como executado / com alvo cria step
# ---------------------------------------------------------------------------

def test_portal_bot_sem_alvo_nao_aparece_nos_steps():
    client = TestClient(app)
    resp = client.post('/api/bots/run', json={'input': '721.377.971-00'})
    ids = [b['bot_id'] for b in resp.json()['bots_executados']]
    assert 'portal_bot' not in ids


def test_portal_bot_no_status_diz_que_precisa_de_alvo():
    client = TestClient(app)
    bots = client.get('/api/bots/status').json()['bots']
    portal = next(b for b in bots if b['bot_id'] == 'portal_bot')
    assert 'alvo' in portal['finalidade'].lower()


CHROME_PATH = '/home/claude/.cache/puppeteer/chrome/linux-131.0.6778.204/chrome-linux64/chrome'
CHROME_DISPONIVEL = __import__('pathlib').Path(CHROME_PATH).exists()


@pytest.mark.skipif(not CHROME_DISPONIVEL, reason='Chrome de teste não encontrado neste ambiente — mecanismo requer navegador real instalado.')
def test_portal_bot_com_alvo_explicito_cria_step(monkeypatch):
    from pathlib import Path
    from app.config import get_settings
    from app.services import captcha_relay
    monkeypatch.setenv('PLAYWRIGHT_CHROME_PATH', CHROME_PATH)
    get_settings.cache_clear()
    fixture_url = 'file://' + str(Path(__file__).parent / 'fixtures' / 'mock_captcha_form.html')
    client = TestClient(app)
    try:
        resp = client.post('/api/bots/run', json={
            'input': 'teste portal', 'portal_url': fixture_url,
            'portal_fill_fields': {'#documento': '123'}, 'portal_submit_selector': '#btnSubmit',
        })
        ids = [b['bot_id'] for b in resp.json()['bots_executados']]
        assert 'portal_bot' in ids
    finally:
        get_settings.cache_clear()
        _fechar_sessoes_pendentes()


@pytest.mark.skipif(not CHROME_DISPONIVEL, reason='Chrome de teste não encontrado neste ambiente — mecanismo requer navegador real instalado.')
def test_job_waiting_user_permanece_ate_resume(monkeypatch):
    from pathlib import Path
    from app.config import get_settings
    monkeypatch.setenv('PLAYWRIGHT_CHROME_PATH', CHROME_PATH)
    get_settings.cache_clear()
    fixture_url = 'file://' + str(Path(__file__).parent / 'fixtures' / 'mock_captcha_form.html')
    client = TestClient(app)
    try:
        resp = client.post('/api/bots/run', json={
            'input': '12345678900', 'portal_url': fixture_url,
            'portal_fill_fields': {'#documento': '12345678900'}, 'portal_submit_selector': '#btnSubmit',
        })
        job_id = resp.json()['job_id']
        assert resp.json()['status'] == 'waiting_user'

        job = client.get(f'/api/bots/jobs/{job_id}').json()
        assert job['status'] == 'waiting_user'
    finally:
        get_settings.cache_clear()
        _fechar_sessoes_pendentes()


def _fechar_sessoes_pendentes():
    """Estes 2 testes deliberadamente deixam uma sessão de navegador
    pausada (é o que estão testando) — sem limpar isso do dicionário global
    SESSIONS, o `active_session_count()` fica poluído pra outros arquivos de
    teste que rodam depois na mesma sessão do pytest (achado real: só
    apareceu rodando a suíte inteira, não este arquivo isolado).

    Só remove do dicionário (sem tentar fechar o browser de forma
    assíncrona aqui) — chamar asyncio.run() de novo logo depois do
    TestClient causava travamento real neste ambiente. O processo do
    Chrome/Node fica órfão até o teardown do processo de teste, o que é
    aceitável neste contexto isolado e descartável."""
    from app.services.captcha_relay import SESSIONS
    SESSIONS.clear()
