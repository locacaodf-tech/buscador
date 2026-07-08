"""v33 — Captação real via importação de publicações. Investigação
concluída: TJGO não tem Diário próprio desde 16/05/2025 (migrou
exclusivamente pro DJEN, confirmado pelo FAQ oficial do TJGO). O Comunica
PJe (comunica.pje.jus.br) é navegável por humano sem login, mas seu
robots.txt desautoriza expressamente acesso automatizado — por isso a
entrega real desta rodada é o IMPORTADOR (colar/estruturado), não um
scraper, que seria uma violação de robots.txt."""
import os

os.environ.setdefault('APP_LOGIN_PASSWORD', '')
os.environ.setdefault('INTERNAL_API_TOKEN', '')

from fastapi.testclient import TestClient

from app.main import app
from app.db import init_db, SessionLocal

init_db()

TEXTO_TJGO_REAL = (
    '📄 Processo: 5419330-39.2022.8.09.0128\n'
    '📌 Polo Passivo: Estado de Goiás\n'
    '📌 Tipo de ação: Horas Extras'
)


def _limpar():
    from app.models import OpportunityLead, PublicationHit, WatcherRun
    db = SessionLocal()
    db.query(OpportunityLead).delete()
    db.query(PublicationHit).delete()
    db.query(WatcherRun).delete()
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Importar publicação realista por texto gera lead
# ---------------------------------------------------------------------------

def test_importar_publicacao_realista_por_texto_gera_lead():
    _limpar()
    client = TestClient(app)
    resp = client.post('/api/watchers/import-publications', json={
        'texto_colado': 'Fica expedido o ofício requisitório em favor do credor, natureza alimentar, INSS.',
        'tribunal': 'TRF1',
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body['total_leads_created'] == 1
    leads = client.get('/api/leads').json()
    assert len(leads) == 1


# ---------------------------------------------------------------------------
# Importar duas vezes não duplica
# ---------------------------------------------------------------------------

def test_importar_duas_vezes_nao_duplica():
    _limpar()
    client = TestClient(app)
    payload = {'texto_colado': TEXTO_TJGO_REAL, 'tribunal': 'TJGO', 'source': 'manual_tjgo'}
    r1 = client.post('/api/watchers/import-publications', json=payload).json()
    r2 = client.post('/api/watchers/import-publications', json=payload).json()
    assert r1['total_leads_created'] == 1
    assert r2['total_leads_created'] == 0
    assert r2['duplicados_ignorados'] == 1
    assert len(client.get('/api/leads').json()) == 1


# ---------------------------------------------------------------------------
# Caso real obrigatório: TJGO/Estado de Goiás/Horas Extras cria lead
# ---------------------------------------------------------------------------

def test_caso_real_tjgo_estado_de_goias_horas_extras_cria_lead_completo():
    _limpar()
    client = TestClient(app)
    resp = client.post('/api/watchers/import-publications', json={
        'texto_colado': TEXTO_TJGO_REAL, 'tribunal': 'TJGO', 'source': 'manual_tjgo',
    })
    assert resp.json()['total_leads_created'] == 1

    lead = client.get('/api/leads').json()[0]
    assert lead['tribunal'] == 'TJGO'
    assert lead['normalized_cnj'] == '5419330-39.2022.8.09.0128'
    assert lead['signal_type'] == 'credito_judicial_potencial'
    assert 'Estado de Goiás' in lead['next_action']
    assert 'Horas Extras' in lead['next_action']


def test_importador_no_formato_estruturado_tambem_funciona():
    _limpar()
    client = TestClient(app)
    resp = client.post('/api/watchers/import-publications', json={
        'publications': [{
            'source': 'manual_tjgo', 'tribunal': 'TJGO', 'publication_date': '2026-07-07',
            'text': TEXTO_TJGO_REAL,
        }],
    })
    body = resp.json()
    assert body['total_leads_created'] == 1
    lead = client.get('/api/leads').json()[0]
    assert lead['normalized_cnj'] == '5419330-39.2022.8.09.0128'


# ---------------------------------------------------------------------------
# Lead aciona bots (via botão/endpoint run-bots, reaproveitado)
# ---------------------------------------------------------------------------

def test_lead_importado_aciona_bots():
    _limpar()
    client = TestClient(app)
    client.post('/api/watchers/import-publications', json={'texto_colado': TEXTO_TJGO_REAL, 'tribunal': 'TJGO'})
    lead_id = client.get('/api/leads').json()[0]['id']
    resp = client.post(f'/api/leads/{lead_id}/run-bots')
    assert resp.status_code == 200
    assert resp.json()['bot_job_id'] is not None


# ---------------------------------------------------------------------------
# Dossiê abre
# ---------------------------------------------------------------------------

def test_dossie_do_lead_importado_abre():
    _limpar()
    client = TestClient(app)
    client.post('/api/watchers/import-publications', json={'texto_colado': TEXTO_TJGO_REAL, 'tribunal': 'TJGO'})
    lead_id = client.get('/api/leads').json()[0]['id']
    dossie = client.get(f'/api/leads/{lead_id}/dossie')
    assert dossie.status_code == 200
    assert 'Goiás' in dossie.text
    assert 'Horas Extras' in dossie.text


# ---------------------------------------------------------------------------
# source_type aparece corretamente
# ---------------------------------------------------------------------------

def test_source_aparece_corretamente_no_csv_e_no_lead():
    _limpar()
    client = TestClient(app)
    client.post('/api/watchers/import-publications', json={
        'texto_colado': TEXTO_TJGO_REAL, 'tribunal': 'TJGO', 'source': 'manual_tjgo',
    })
    csv_resp = client.get('/api/leads/export.csv')
    assert csv_resp.status_code == 200
    assert 'manual_tjgo' in csv_resp.text
    assert 'TJGO' in csv_resp.text
    assert 'Estado de Goiás' in csv_resp.text
    assert 'Horas Extras' in csv_resp.text


# ---------------------------------------------------------------------------
# CSV exporta com todos os campos pedidos
# ---------------------------------------------------------------------------

def test_csv_tem_todos_os_campos_pedidos():
    _limpar()
    client = TestClient(app)
    client.post('/api/watchers/import-publications', json={'texto_colado': TEXTO_TJGO_REAL, 'tribunal': 'TJGO'})
    csv_resp = client.get('/api/leads/export.csv')
    header = csv_resp.text.split('\r\n')[0]
    for campo in ['data', 'fonte', 'tribunal', 'cnj', 'ente_devedor', 'tipo_de_acao', 'sinal', 'prioridade', 'score', 'proxima_acao', 'link_dossie']:
        assert campo in header


# ---------------------------------------------------------------------------
# Múltiplas publicações num bloco só (separadas por linha em branco dupla)
# ---------------------------------------------------------------------------

def test_multiplas_publicacoes_em_um_bloco_colado():
    _limpar()
    client = TestClient(app)
    bloco = (
        'Fica expedido o ofício requisitório em favor do credor.\n\n\n'
        'Homologo os cálculos apresentados pelo contador.'
    )
    resp = client.post('/api/watchers/import-publications', json={'texto_colado': bloco, 'tribunal': 'TJGO'})
    body = resp.json()
    assert body['total_publicacoes_recebidas'] == 2


# ---------------------------------------------------------------------------
# Não expõe CPF completo
# ---------------------------------------------------------------------------

def test_importacao_nao_expoe_cpf_completo():
    _limpar()
    client = TestClient(app)
    client.post('/api/watchers/import-publications', json={
        'texto_colado': TEXTO_TJGO_REAL + '\nCPF do reclamante: 123.456.789-09.', 'tribunal': 'TJGO',
    })
    lead_id = client.get('/api/leads').json()[0]['id']
    dossie = client.get(f'/api/leads/{lead_id}/dossie')
    assert '123.456.789-09' not in dossie.text
    csv_resp = client.get('/api/leads/export.csv')
    assert '123.456.789-09' not in csv_resp.text
