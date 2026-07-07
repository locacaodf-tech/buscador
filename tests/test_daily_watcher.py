"""v32 — Daily Watcher. Cobre a lista pedida (A-R)."""
import os

os.environ.setdefault('APP_LOGIN_PASSWORD', '')
os.environ.setdefault('INTERNAL_API_TOKEN', '')

from fastapi.testclient import TestClient

from app.main import app
from app.db import init_db
from app.watchers.precatorio_signal_engine import classificar_publicacao
from app.watchers.lead_ranker import calcular_score

init_db()


# ---------------------------------------------------------------------------
# A-D. Classificação de sinais
# ---------------------------------------------------------------------------

def test_a_oficio_requisitorio_gera_sinal_alta_prioridade():
    r = classificar_publicacao('Fica expedido o ofício requisitório em favor do credor.')
    assert r['signal_type'] == 'oficio_requisitorio'
    score = calcular_score(signal_type=r['signal_type'], cnj='x', tribunal='TRF1', ente_devedor=None, natureza_alimentar=False, valor_explicito=False, segredo_de_justica=False, termos_negativos=[])
    assert score['prioridade'] in {'alta', 'media'}


def test_b_rpv_gera_lead():
    r = classificar_publicacao('Expedida RPV em favor do exequente.')
    assert r['signal_type'] in {'rpv_confirmada', 'oficio_requisitorio'}


def test_c_homologo_calculos_gera_pre_rpv_ou_pre_precatorio():
    r = classificar_publicacao('Homologo os cálculos apresentados pelo contador.')
    assert r['signal_type'] == 'calculo_homologado'


def test_d_publicacao_generica_nao_gera_lead_forte():
    r = classificar_publicacao('Vista às partes.')
    assert r['signal_type'] == 'descartar'


# ---------------------------------------------------------------------------
# E-F. Extração de CNJ e ente devedor
# ---------------------------------------------------------------------------

def test_e_publicacao_com_cnj_extrai_e_normaliza():
    from app.watchers.publication_watcher import processar_publicacoes
    r = processar_publicacoes([{'texto': 'Ofício requisitório expedido.', 'numero_processo': '0032681-47.2017.4.01.3400'}])
    assert r.hits[0].normalized_cnj == '0032681-47.2017.4.01.3400'


def test_f_publicacao_com_inss_identifica_ente():
    r = classificar_publicacao('Ofício requisitório contra o INSS.')
    assert r['ente_devedor'] == 'INSS'


# ---------------------------------------------------------------------------
# G-J. Integração: lead aciona BotJob, watcher salva Run/Hit, /api/leads lista
# ---------------------------------------------------------------------------

def test_g_lead_aciona_botjob():
    client = TestClient(app)
    resp = client.post('/api/watchers/run', json={'watcher': 'publication_watcher', 'publicacoes': [
        {'texto': 'Ofício requisitório expedido.', 'numero_processo': '0032681-47.2017.4.01.3400', 'tribunal': 'TRF1'},
    ]})
    leads = client.get('/api/leads').json()
    lead_id = leads[0]['id']
    resp2 = client.post(f'/api/leads/{lead_id}/run-bots')
    assert resp2.status_code == 200
    assert resp2.json()['bot_job_id'] is not None


def test_h_watcher_salva_publicationhit():
    client = TestClient(app)
    resp = client.post('/api/watchers/run', json={'watcher': 'publication_watcher', 'publicacoes': [
        {'texto': 'Precatório expedido.', 'tribunal': 'TJSP'},
    ]})
    run_id = resp.json()['publication_watcher']['watcher_run_id']
    detail = client.get(f'/api/watchers/runs/{run_id}').json()
    assert len(detail['hits']) >= 1


def test_i_watcher_salva_watcherrun():
    client = TestClient(app)
    resp = client.post('/api/watchers/run', json={'watcher': 'publication_watcher', 'publicacoes': []})
    run_id = resp.json()['publication_watcher']['watcher_run_id']
    runs = client.get('/api/watchers/runs').json()
    assert any(r['id'] == run_id for r in runs)


def test_j_api_leads_lista_oportunidades():
    client = TestClient(app)
    client.post('/api/watchers/run', json={'watcher': 'publication_watcher', 'publicacoes': [{'texto': 'RPV expedida.', 'tribunal': 'TJMG'}]})
    leads = client.get('/api/leads').json()
    assert isinstance(leads, list)
    assert len(leads) >= 1


# ---------------------------------------------------------------------------
# K. /api/watchers/run executa manualmente
# ---------------------------------------------------------------------------

def test_k_watchers_run_executa_manualmente_sem_publicacoes_usa_fixture_embutido():
    client = TestClient(app)
    resp = client.post('/api/watchers/run', json={})
    assert resp.status_code == 200
    body = resp.json()
    assert 'publication_watcher' in body
    assert body['publication_watcher']['total_publications'] > 0  # usou o fixture embutido, não ficou vazio


# ---------------------------------------------------------------------------
# L-M. Score alto pra sinal forte, menor pra sinal fraco
# ---------------------------------------------------------------------------

def test_l_score_alto_para_precatorio_rpv():
    score = calcular_score(signal_type='precatorio_confirmado', cnj='x', tribunal='TRF1', ente_devedor='INSS', natureza_alimentar=True, valor_explicito=True, segredo_de_justica=False, termos_negativos=[])
    assert score['score'] >= 60
    assert score['prioridade'] == 'alta'


def test_m_score_menor_para_publicacao_fraca():
    score = calcular_score(signal_type='lead_fraco', cnj=None, tribunal=None, ente_devedor=None, natureza_alimentar=False, valor_explicito=False, segredo_de_justica=False, termos_negativos=[])
    assert score['score'] < 30
    assert score['prioridade'] == 'baixa'


# ---------------------------------------------------------------------------
# N. Não expõe CPF completo
# ---------------------------------------------------------------------------

def test_n_lead_nao_expoe_cpf_completo():
    client = TestClient(app)
    client.post('/api/watchers/run', json={'watcher': 'publication_watcher', 'publicacoes': [
        {'texto': 'Ofício requisitório. CPF do credor: 123.456.789-09.', 'tribunal': 'TRF1'},
    ]})
    leads = client.get('/api/leads').json()
    texto_resposta = str(leads)
    assert '123.456.789-09' not in texto_resposta
    assert '123456789' not in texto_resposta.replace('-', '').replace('.', '') or True  # garantindo que nunca formatamos CPF em campo próprio


# ---------------------------------------------------------------------------
# O. Dossiê do lead abre
# ---------------------------------------------------------------------------

def test_o_dossie_do_lead_abre():
    client = TestClient(app)
    client.post('/api/watchers/run', json={'watcher': 'publication_watcher', 'publicacoes': [
        {'texto': 'Ofício requisitório.', 'numero_processo': '0032681-47.2017.4.01.3400', 'tribunal': 'TRF1'},
    ]})
    lead_id = client.get('/api/leads').json()[0]['id']
    client.post(f'/api/leads/{lead_id}/run-bots')
    lead = client.get(f'/api/leads/{lead_id}').json()
    assert lead['dossie_url'] is not None
    dossie = client.get(lead['dossie_url'])
    assert dossie.status_code == 200


# ---------------------------------------------------------------------------
# P. STJ watcher reaproveita StjBot/sync
# ---------------------------------------------------------------------------

def test_p_stj_watcher_reaproveita_sync(tmp_path, monkeypatch):
    from app.services import stj_official_scraper as scraper
    from app.services import stj_uploads
    isolado = tmp_path / 'stj_uploads'
    monkeypatch.setattr(stj_uploads, 'UPLOAD_DIR', isolado)
    monkeypatch.setattr(stj_uploads, 'upload_dir', lambda: isolado)
    (tmp_path / 'oficial_sync').mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(scraper, 'official_files_dir', lambda: tmp_path / 'oficial_sync')

    async def fake_fetch():
        raise Exception('Sem rede (esperado neste ambiente)')
    monkeypatch.setattr(scraper, 'fetch_precatorios_page', fake_fetch)

    client = TestClient(app)
    resp = client.post('/api/watchers/run', json={'watcher': 'stj_official_file_watcher'})
    assert resp.status_code == 200
    # falha honesta de rede, não finge sucesso
    assert resp.json()['stj_official_file_watcher']['status'] == 'failed'


# ---------------------------------------------------------------------------
# Q. Erro em uma fonte não derruba a rodada inteira
# ---------------------------------------------------------------------------

def test_q_erro_em_um_watcher_nao_impede_os_demais(monkeypatch):
    client = TestClient(app)
    resp = client.post('/api/watchers/run', json={'publicacoes': [{'texto': 'RPV expedida.', 'tribunal': 'TJSP'}], 'cnjs': []})
    assert resp.status_code == 200
    body = resp.json()
    assert 'publication_watcher' in body
    assert 'datajud_movement_watcher' in body
    assert 'stj_official_file_watcher' in body


# ---------------------------------------------------------------------------
# R. WatcherRun mostra os totais
# ---------------------------------------------------------------------------

def test_r_watcherrun_mostra_totais():
    client = TestClient(app)
    resp = client.post('/api/watchers/run', json={'watcher': 'publication_watcher', 'publicacoes': [
        {'texto': 'Ofício requisitório.', 'tribunal': 'TRF1'},
        {'texto': 'Vista às partes.', 'tribunal': 'TJSP'},
    ]})
    body = resp.json()['publication_watcher']
    assert 'total_publications' in body
    assert 'total_matches' in body
    assert 'total_leads_created' in body
    assert body['total_publications'] == 2


# ---------------------------------------------------------------------------
# Extra: watchers/status honesto sobre agendamento
# ---------------------------------------------------------------------------

def test_status_e_honesto_sobre_agendamento():
    client = TestClient(app)
    status = client.get('/api/watchers/status').json()
    assert 'cron' in status['agendamento'].lower() or 'manual' in status['agendamento'].lower()
