"""v32.1 — Maturação do Daily Watcher. Cobre a lista pedida (A-J):
deduplicação real, auto-run-bots configurável, dossiê do lead sem
bot_job_id, overall_status honesto."""
import os

os.environ.setdefault('APP_LOGIN_PASSWORD', '')
os.environ.setdefault('INTERNAL_API_TOKEN', '')

from fastapi.testclient import TestClient

from app.main import app
from app.db import init_db, SessionLocal

init_db()


def _limpar_leads_e_hits():
    from app.models import OpportunityLead, PublicationHit, WatcherRun
    db = SessionLocal()
    db.query(OpportunityLead).delete()
    db.query(PublicationHit).delete()
    db.query(WatcherRun).delete()
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# A) watcher run com fixture cria leads
# ---------------------------------------------------------------------------

def test_a_watcher_run_com_fixture_cria_leads():
    _limpar_leads_e_hits()
    client = TestClient(app)
    resp = client.post('/api/watchers/run', json={'watcher': 'publication_watcher', 'publicacoes': [
        {'texto': 'Ofício requisitório expedido.', 'tribunal': 'TRF1', 'numero_processo': '0032681-47.2017.4.01.3400'},
    ]})
    body = resp.json()
    assert body['watchers']['publication_watcher']['total_leads_created'] == 1
    leads = client.get('/api/leads').json()
    assert len(leads) >= 1


# ---------------------------------------------------------------------------
# B) rodar duas vezes não duplica
# ---------------------------------------------------------------------------

def test_b_rodar_duas_vezes_nao_duplica():
    _limpar_leads_e_hits()
    client = TestClient(app)
    pubs = [{'texto': 'Ofício requisitório expedido, natureza alimentar.', 'tribunal': 'TRF1', 'numero_processo': '0032681-47.2017.4.01.3400', 'data': '2026-07-07'}]
    r1 = client.post('/api/watchers/run', json={'watcher': 'publication_watcher', 'publicacoes': pubs}).json()
    r2 = client.post('/api/watchers/run', json={'watcher': 'publication_watcher', 'publicacoes': pubs}).json()
    assert r1['watchers']['publication_watcher']['total_leads_created'] == 1
    assert r2['watchers']['publication_watcher']['total_leads_created'] == 0
    assert r2['watchers']['publication_watcher']['duplicados_ignorados'] == 1
    leads = client.get('/api/leads').json()
    assert len(leads) == 1


def test_b2_seen_count_e_last_seen_at_atualizam():
    _limpar_leads_e_hits()
    client = TestClient(app)
    pubs = [{'texto': 'RPV expedida em favor do credor.', 'tribunal': 'TJMG', 'numero_processo': '0032681-47.2017.4.01.3400', 'data': '2026-07-07'}]
    client.post('/api/watchers/run', json={'watcher': 'publication_watcher', 'publicacoes': pubs})
    client.post('/api/watchers/run', json={'watcher': 'publication_watcher', 'publicacoes': pubs})
    client.post('/api/watchers/run', json={'watcher': 'publication_watcher', 'publicacoes': pubs})

    from app.models import OpportunityLead
    db = SessionLocal()
    lead = db.query(OpportunityLead).first()
    assert lead.seen_count == 3
    assert lead.first_seen_at is not None
    assert lead.last_seen_at is not None
    db.close()


# ---------------------------------------------------------------------------
# C) lead dossiê abre sem bot_job_id
# ---------------------------------------------------------------------------

def test_c_lead_dossie_abre_sem_bot_job_id():
    _limpar_leads_e_hits()
    client = TestClient(app)
    client.post('/api/watchers/run', json={'watcher': 'publication_watcher', 'publicacoes': [
        {'texto': 'Ofício requisitório expedido.', 'tribunal': 'TRF1'},
    ]})
    lead = client.get('/api/leads').json()[0]
    assert lead['bot_job_id'] is None
    resp = client.get(f'/api/leads/{lead["id"]}/dossie')
    assert resp.status_code == 200
    assert 'Bots ainda não rodaram' in resp.text


def test_c2_dossie_de_lead_inexistente_devolve_404():
    client = TestClient(app)
    assert client.get('/api/leads/999999/dossie').status_code == 404


# ---------------------------------------------------------------------------
# D-E) auto-run-bots desligado/ligado
# ---------------------------------------------------------------------------

def test_d_auto_run_bots_desligado_nao_cria_bot_job_id(monkeypatch):
    _limpar_leads_e_hits()
    from app.config import get_settings
    monkeypatch.setenv('WATCHERS_AUTO_RUN_BOTS', 'false')
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        client.post('/api/watchers/run', json={'watcher': 'publication_watcher', 'publicacoes': [
            {'texto': 'Ofício requisitório expedido.', 'tribunal': 'TRF1', 'numero_processo': '0032681-47.2017.4.01.3400'},
        ]})
        leads = client.get('/api/leads').json()
        assert all(l['bot_job_id'] is None for l in leads)
    finally:
        get_settings.cache_clear()


def test_e_auto_run_bots_ligado_cria_bot_job_id_para_alta_prioridade(monkeypatch):
    _limpar_leads_e_hits()
    from app.config import get_settings
    monkeypatch.setenv('WATCHERS_AUTO_RUN_BOTS', 'true')
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        client.post('/api/watchers/run', json={'watcher': 'publication_watcher', 'publicacoes': [
            {'texto': 'Ofício requisitório expedido, natureza alimentar, INSS, valor de R$ 50.000.', 'tribunal': 'TRF1', 'numero_processo': '0032681-47.2017.4.01.3400'},
            {'texto': 'Vista às partes para manifestação.', 'tribunal': 'TJSP', 'numero_processo': None},
        ]})
        leads = client.get('/api/leads').json()
        lead_alta = next(l for l in leads if l['priority'] == 'alta')
        assert lead_alta['bot_job_id'] is not None
    finally:
        get_settings.cache_clear()


def test_e2_lead_media_baixa_fica_manual_mesmo_com_auto_run_ligado(monkeypatch):
    _limpar_leads_e_hits()
    from app.config import get_settings
    monkeypatch.setenv('WATCHERS_AUTO_RUN_BOTS', 'true')
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        client.post('/api/watchers/run', json={'watcher': 'publication_watcher', 'publicacoes': [
            {'texto': 'Homologo os cálculos apresentados.', 'tribunal': 'TJBA', 'numero_processo': '8000694-09.2025.8.05.0043'},
        ]})
        leads = client.get('/api/leads').json()
        lead = leads[0]
        assert lead['priority'] != 'alta'
        assert lead['bot_job_id'] is None
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# F) WatcherRun registra duplicados
# ---------------------------------------------------------------------------

def test_f_watcherrun_registra_duplicados():
    _limpar_leads_e_hits()
    client = TestClient(app)
    pubs = [{'texto': 'Precatório expedido.', 'tribunal': 'TJSP', 'numero_processo': '0032681-47.2017.4.01.3400', 'data': '2026-07-07'}]
    client.post('/api/watchers/run', json={'watcher': 'publication_watcher', 'publicacoes': pubs})
    r2 = client.post('/api/watchers/run', json={'watcher': 'publication_watcher', 'publicacoes': pubs}).json()
    assert r2['watchers']['publication_watcher']['duplicados_ignorados'] == 1


# ---------------------------------------------------------------------------
# G) overall_status vira partial se um watcher falhar
# ---------------------------------------------------------------------------

def test_g_overall_status_vira_partial_se_um_watcher_falhar():
    _limpar_leads_e_hits()
    client = TestClient(app)
    resp = client.post('/api/watchers/run', json={'publicacoes': [{'texto': 'Ofício requisitório.', 'tribunal': 'TRF1'}]})
    body = resp.json()
    # STJ watcher falha por rede neste ambiente (sandbox sem acesso a stj.jus.br)
    assert body['overall_status'] == 'partial'
    assert body['watchers']['stj_official_file_watcher']['status'] == 'failed'
    assert body['watchers']['publication_watcher']['status'] == 'completed'


# ---------------------------------------------------------------------------
# H) /api/watchers/status mostra cron externo e bots automáticos
# ---------------------------------------------------------------------------

def test_h_watchers_status_mostra_cron_e_bots_automaticos():
    client = TestClient(app)
    status = client.get('/api/watchers/status').json()
    assert status['agendamento']['cron_nativo_ativo'] is False
    assert 'cron-job.org' in status['agendamento']['alternativa_gratuita'] or 'cron' in status['agendamento']['alternativa_gratuita'].lower()
    assert 'bots_automaticos' in status
    assert 'ativado' in status['bots_automaticos']


# ---------------------------------------------------------------------------
# I) tela mostra "bots automáticos desativados" quando false — verificado
# via conteúdo da resposta da API que a tela consome diretamente.
# ---------------------------------------------------------------------------

def test_i_status_texto_menciona_desativado_por_padrao():
    client = TestClient(app)
    status = client.get('/api/watchers/status').json()
    assert status['bots_automaticos']['ativado'] is False
    assert 'desativados' in status['bots_automaticos']['descricao']


# ---------------------------------------------------------------------------
# J) CPF completo não aparece nos leads
# ---------------------------------------------------------------------------

def test_j_cpf_completo_nao_aparece_nos_leads():
    _limpar_leads_e_hits()
    client = TestClient(app)
    client.post('/api/watchers/run', json={'watcher': 'publication_watcher', 'publicacoes': [
        {'texto': 'Ofício requisitório. CPF do credor: 123.456.789-09.', 'tribunal': 'TRF1'},
    ]})
    leads_resposta = client.get('/api/leads')
    assert '123.456.789-09' not in leads_resposta.text
    lead_id = leads_resposta.json()[0]['id']
    detalhe = client.get(f'/api/leads/{lead_id}')
    assert '123.456.789-09' not in detalhe.text
    dossie = client.get(f'/api/leads/{lead_id}/dossie')
    assert '123.456.789-09' not in dossie.text
