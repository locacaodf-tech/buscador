"""v32.2 — Hotfix de intake real + lead manual. Caso real reportado:
mensagem com emojis (📄 Processo:, 📌 Polo Passivo:, 📌 Tipo de ação:) não
gerava lead nenhum, mesmo tendo CNJ + ente público + tipo de ação
suficientes pra virar uma diligência operacional."""
import os

os.environ.setdefault('APP_LOGIN_PASSWORD', '')
os.environ.setdefault('INTERNAL_API_TOKEN', '')

from fastapi.testclient import TestClient

from app.main import app
from app.db import init_db
from app.services import whatsapp_intake

init_db()

TEXTO_REAL_REPORTADO = (
    '📄 Processo: 5419330-39.2022.8.09.0128\n'
    '📌 Polo Passivo: Estado de Goiás\n'
    '📌 Tipo de ação: Horas Extras'
)


# ---------------------------------------------------------------------------
# A) Mensagem com emojis extrai CNJ
# ---------------------------------------------------------------------------

def test_a_mensagem_com_emojis_extrai_cnj():
    r = whatsapp_intake.processar_mensagem(TEXTO_REAL_REPORTADO)
    assert r['processos_detectados'][0]['cnj_normalizado'] == '5419330-39.2022.8.09.0128'


# ---------------------------------------------------------------------------
# B) "Polo Passivo: Estado de Goiás" extrai ente devedor (nome completo)
# ---------------------------------------------------------------------------

def test_b_polo_passivo_extrai_ente_devedor_completo():
    r = whatsapp_intake.processar_mensagem(TEXTO_REAL_REPORTADO)
    assert r['ente_devedor'] == 'Estado de Goiás'


# ---------------------------------------------------------------------------
# C) "Tipo de ação: Horas Extras" extrai tipo de ação
# ---------------------------------------------------------------------------

def test_c_tipo_de_acao_extraido():
    r = whatsapp_intake.processar_mensagem(TEXTO_REAL_REPORTADO)
    assert r['tipo_acao'] == 'Horas Extras'


# ---------------------------------------------------------------------------
# D) CNJ 8.09 infere TJGO
# ---------------------------------------------------------------------------

def test_d_cnj_809_infere_tjgo():
    r = whatsapp_intake.processar_mensagem(TEXTO_REAL_REPORTADO)
    assert r['processos_detectados'][0]['tribunal_provavel'] == 'TJGO'
    assert r['processos_detectados'][0]['segmento_nome'] == 'Justiça Estadual'


# ---------------------------------------------------------------------------
# E-F) Mesmo com DataJud vazio/erro, cria lead
# ---------------------------------------------------------------------------

def test_e_datajud_vazio_ainda_assim_cria_lead(monkeypatch):
    async def fake_search(self, search_type, search_key, **kwargs):
        return []
    monkeypatch.setattr('app.connectors.datajud.DataJudConnector.search', fake_search)

    client = TestClient(app)
    resp = client.post('/api/intake/whatsapp/manual', json={'texto': TEXTO_REAL_REPORTADO})
    body = resp.json()
    assert body['opportunity_lead_id'] is not None


def test_f_datajud_com_erro_ainda_assim_cria_lead(monkeypatch):
    async def fake_search_falha(self, search_type, search_key, **kwargs):
        raise Exception('Falha de rede simulada')
    monkeypatch.setattr('app.connectors.datajud.DataJudConnector.search', fake_search_falha)

    client = TestClient(app)
    resp = client.post('/api/intake/whatsapp/manual', json={'texto': TEXTO_REAL_REPORTADO})
    body = resp.json()
    assert body['opportunity_lead_id'] is not None


# ---------------------------------------------------------------------------
# G) Lead aciona BotJob
# ---------------------------------------------------------------------------

def test_g_lead_aciona_botjob():
    from app.db import SessionLocal
    from app.models import OpportunityLead
    db = SessionLocal()
    db.query(OpportunityLead).delete()
    db.commit()
    db.close()

    client = TestClient(app)
    resp = client.post('/api/intake/whatsapp/manual', json={'texto': TEXTO_REAL_REPORTADO})
    body = resp.json()
    assert body['job_id'] is not None
    lead = client.get(f"/api/leads/{body['opportunity_lead_id']}").json()
    assert lead['bot_job_id'] == body['job_id']


# ---------------------------------------------------------------------------
# H) Dossiê mostra Estado de Goiás e Horas Extras
# ---------------------------------------------------------------------------

def test_h_dossie_mostra_estado_de_goias_e_horas_extras():
    client = TestClient(app)
    resp = client.post('/api/intake/whatsapp/manual', json={'texto': TEXTO_REAL_REPORTADO})
    lead_id = resp.json()['opportunity_lead_id']
    dossie = client.get(f'/api/leads/{lead_id}/dossie')
    assert 'Goiás' in dossie.text
    assert 'Horas Extras' in dossie.text
    assert 'TJGO' in dossie.text


# ---------------------------------------------------------------------------
# I) Mensagem visual não diz apenas "não encontrado"
# ---------------------------------------------------------------------------

def test_i_mensagem_visual_nao_diz_apenas_nao_encontrado(monkeypatch):
    async def fake_search(self, search_type, search_key, **kwargs):
        return []
    monkeypatch.setattr('app.connectors.datajud.DataJudConnector.search', fake_search)

    client = TestClient(app)
    resp = client.post('/api/intake/whatsapp/manual', json={'texto': TEXTO_REAL_REPORTADO})
    proxima_acao = resp.json()['proxima_acao']
    assert proxima_acao.strip().lower() != 'não encontramos esse processo no datajud.'
    assert 'TJGO' in proxima_acao
    assert 'Estado de Goiás' in proxima_acao


# ---------------------------------------------------------------------------
# J) OpportunityLead aparece em /api/leads
# ---------------------------------------------------------------------------

def test_j_opportunitylead_aparece_em_api_leads():
    client = TestClient(app)
    resp = client.post('/api/intake/whatsapp/manual', json={'texto': TEXTO_REAL_REPORTADO})
    lead_id = resp.json()['opportunity_lead_id']
    leads = client.get('/api/leads').json()
    assert any(l['id'] == lead_id for l in leads)
    lead = next(l for l in leads if l['id'] == lead_id)
    assert lead['tribunal'] == 'TJGO'
    assert lead['normalized_cnj'] == '5419330-39.2022.8.09.0128'


# ---------------------------------------------------------------------------
# K) CPF/CNPJ, se houver, continuam mascarados
# ---------------------------------------------------------------------------

def test_k_cpf_continua_mascarado_mesmo_neste_novo_fluxo():
    client = TestClient(app)
    texto_com_cpf = TEXTO_REAL_REPORTADO + '\nCPF do reclamante: 123.456.789-09.'
    resp = client.post('/api/intake/whatsapp/manual', json={'texto': texto_com_cpf})
    assert '123.456.789-09' not in resp.text
    lead_id = resp.json()['opportunity_lead_id']
    dossie = client.get(f'/api/leads/{lead_id}/dossie')
    assert '123.456.789-09' not in dossie.text


# ---------------------------------------------------------------------------
# L) Emojis não quebram o parser (rótulos alternativos também funcionam)
# ---------------------------------------------------------------------------

def test_l_emojis_nao_quebram_e_rotulos_alternativos_funcionam():
    variantes = [
        'Processo: 5419330-39.2022.8.09.0128\nPolo passivo: Estado de Goiás\nAssunto: Horas Extras',
        'Número do processo: 5419330-39.2022.8.09.0128\nExecutado: Estado de Goiás\nClasse: Horas Extras',
        '📄 Processo: 5419330-39.2022.8.09.0128 📌 Polo Passivo: Estado de Goiás 📌 Tipo de ação: Horas Extras',
    ]
    for texto in variantes:
        r = whatsapp_intake.processar_mensagem(texto)
        assert r['processos_detectados'], f'falhou pra: {texto}'
        assert r['ente_devedor'] is not None, f'ente_devedor nulo pra: {texto}'


# ---------------------------------------------------------------------------
# Deduplicação: mesma mensagem duas vezes não duplica o lead
# ---------------------------------------------------------------------------

def test_mesma_mensagem_duas_vezes_nao_duplica_lead():
    client = TestClient(app)
    r1 = client.post('/api/intake/whatsapp/manual', json={'texto': TEXTO_REAL_REPORTADO}).json()
    r2 = client.post('/api/intake/whatsapp/manual', json={'texto': TEXTO_REAL_REPORTADO}).json()
    assert r1['opportunity_lead_id'] == r2['opportunity_lead_id']


def test_duplicata_exata_nao_roda_bots_de_novo():
    """Achado real: rodar a MESMA mensagem duas vezes criava um BotJob
    novo (gastando chamada de DataJud à toa) mesmo o lead sendo
    corretamente deduplicado. Agora a segunda chamada reaproveita o job
    já existente, sem rodar bots de novo."""
    from app.db import SessionLocal
    from app.models import OpportunityLead
    db = SessionLocal()
    db.query(OpportunityLead).delete()
    db.commit()
    db.close()

    client = TestClient(app)
    r1 = client.post('/api/intake/whatsapp/manual', json={'texto': TEXTO_REAL_REPORTADO}).json()
    r2 = client.post('/api/intake/whatsapp/manual', json={'texto': TEXTO_REAL_REPORTADO}).json()
    assert r1['job_id'] is not None
    assert r2['job_id'] is None  # não rodou bots de novo, é duplicata exata
    lead = client.get(f"/api/leads/{r1['opportunity_lead_id']}").json()
    assert lead['bot_job_id'] == r1['job_id']  # continua apontando pro job original
