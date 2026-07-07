"""v31g — CNJ com sufixo vira regra GLOBAL (não só do IntakeBot) + prioridade
documental na próxima ação. Achados reais de auditoria externa:
1. infer_identifier() (usado por /api/diligencia, /api/bots/run, /api/search)
   usava only_digits() cru, nunca passou pelo fix de sufixo aplicado só em
   whatsapp_intake.py — corrigido pra usar normalize_cnj/split_cnj_suffix.
2. A checagem de "DataJud sem resultado" só olhava job.status in
   {partial, failed}, mas uma consulta bem-sucedida e vazia deixa o job
   'completed' — corrigido pra checar o status_consulta real do step."""
import os

os.environ.setdefault('APP_LOGIN_PASSWORD', '')
os.environ.setdefault('INTERNAL_API_TOKEN', '')

from fastapi.testclient import TestClient

from app.main import app
from app.db import init_db
from app.services.identifier import infer_identifier

init_db()

CNJ_COM_SUFIXO = '0016114-59.2017.8.26.0053/01'
TEXTO_OFICIO_REQUISITORIO = (
    '0016114-59.2017.8.26.0053/01\n'
    'Ofício Requisitório nº 2149/2019\n'
    'Fazenda Pública do Estado de São Paulo'
)
TEXTO_ACAO_RESCISORIA = (
    'Número: 8045581-76.2026.8.05.0000\n'
    'Classe: AÇÃO RESCISÓRIA\n'
    'Processo referência: 8000694-09.2025.8.05.0043'
)


def _mock_datajud_vazio(monkeypatch):
    async def fake_search(self, search_type, search_key, **kwargs):
        return []
    monkeypatch.setattr('app.connectors.datajud.DataJudConnector.search', fake_search)


# ---------------------------------------------------------------------------
# 1-2. /api/diligencia identifica CNJ com sufixo e consulta com o CNJ base
# ---------------------------------------------------------------------------

def test_1_diligencia_identifica_cnj_com_sufixo():
    client = TestClient(app)
    resp = client.post('/api/diligencia', json={'input': CNJ_COM_SUFIXO})
    body = resp.json()
    assert body['tipo_identificado'] == 'cnj'
    assert body['valor_normalizado'] == '00161145920178260053'


def test_2_diligencia_consulta_datajud_com_cnj_base(monkeypatch):
    chamadas = []

    async def fake_search_by_cnj(self, cnj, tribunals=None, max_results=50):
        chamadas.append(cnj)
        return []

    monkeypatch.setattr('app.connectors.datajud.DataJudConnector.search_by_cnj', fake_search_by_cnj)
    client = TestClient(app)
    client.post('/api/diligencia', json={'input': CNJ_COM_SUFIXO})
    assert all(len(c) == 20 for c in chamadas if c)


# ---------------------------------------------------------------------------
# 3. /api/search com CNJ + /01 também usa CNJ base
# ---------------------------------------------------------------------------

def test_3_search_identifica_cnj_com_sufixo():
    client = TestClient(app)
    resp = client.post('/api/search', json={'search_key': CNJ_COM_SUFIXO, 'search_type': 'auto'})
    body = resp.json()
    assert body['search_type'] == 'cnj'


# ---------------------------------------------------------------------------
# 4. DataJudBot com CNJ + /01 usa CNJ base
# ---------------------------------------------------------------------------

def test_4_datajudbot_via_bots_run_usa_cnj_base(monkeypatch):
    chamadas = []

    async def fake_search_by_cnj(self, cnj, tribunals=None, max_results=50):
        chamadas.append(cnj)
        return []

    monkeypatch.setattr('app.connectors.datajud.DataJudConnector.search_by_cnj', fake_search_by_cnj)
    client = TestClient(app)
    resp = client.post('/api/bots/run', json={'input': CNJ_COM_SUFIXO})
    body = resp.json()
    assert body['tipo_identificado'] == 'cnj'
    datajud_step = next(b for b in body['bots_executados'] if b['bot_id'] == 'datajud_bot')
    assert datajud_step is not None
    assert all(len(c) == 20 for c in chamadas if c)


# ---------------------------------------------------------------------------
# 5. Resolução central (infer_identifier) mostra CNJ base + sufixo + tribunal
# ---------------------------------------------------------------------------

def test_5_infer_identifier_devolve_cnj_base_e_sufixo():
    r = infer_identifier(CNJ_COM_SUFIXO)
    assert r.search_type == 'cnj'
    assert r.search_key == '00161145920178260053'
    assert r.sufixo == '01'


def test_5b_infer_identifier_sem_sufixo_continua_normal():
    r = infer_identifier('5000563-34.2022.4.03.6331')
    assert r.search_type == 'cnj'
    assert r.sufixo is None


# ---------------------------------------------------------------------------
# 6. IntakeBot continua funcionando (regressão)
# ---------------------------------------------------------------------------

def test_6_intakebot_continua_funcionando(monkeypatch):
    _mock_datajud_vazio(monkeypatch)
    client = TestClient(app)
    resp = client.post('/api/intake/whatsapp/manual', json={'texto': TEXTO_OFICIO_REQUISITORIO})
    assert resp.status_code == 200
    body = resp.json()
    assert body['classe_documento'] == 'Ofício Requisitório'


# ---------------------------------------------------------------------------
# 7. Ofício requisitório + DataJud vazio (não erro) gera próxima ação TJSP/DEPRE
# ---------------------------------------------------------------------------

def test_7_datajud_vazio_com_oficio_requisitorio_gera_mensagem_tjsp_depre(monkeypatch):
    _mock_datajud_vazio(monkeypatch)
    client = TestClient(app)
    resp = client.post('/api/intake/whatsapp/manual', json={'texto': TEXTO_OFICIO_REQUISITORIO})
    body = resp.json()
    assert 'TJSP' in body['proxima_acao']
    assert 'DEPRE' in body['proxima_acao']
    assert body['proxima_acao'] != 'Peça também: CPF ou CNPJ, Nome completo'


# ---------------------------------------------------------------------------
# 8. Ação rescisória + processo referência + DataJud vazio (não erro) gera
# próxima ação sobre processo referência
# ---------------------------------------------------------------------------

def test_8_datajud_vazio_com_acao_rescisoria_gera_mensagem_processo_referencia(monkeypatch):
    _mock_datajud_vazio(monkeypatch)
    client = TestClient(app)
    resp = client.post('/api/intake/whatsapp/manual', json={'texto': TEXTO_ACAO_RESCISORIA})
    body = resp.json()
    assert 'ação rescisória' in body['proxima_acao'].lower()
    assert '8000694-09.2025.8.05.0043' in body['proxima_acao']
    assert body['proxima_acao'] != 'Peça também: CPF ou CNPJ, Nome completo'


# ---------------------------------------------------------------------------
# 9. "Peça CPF/nome" nunca ganha de contexto documental forte
# ---------------------------------------------------------------------------

def test_9_peca_cpf_nome_nunca_ganha_de_contexto_documental_forte(monkeypatch):
    _mock_datajud_vazio(monkeypatch)
    client = TestClient(app)
    for texto in [TEXTO_OFICIO_REQUISITORIO, TEXTO_ACAO_RESCISORIA]:
        resp = client.post('/api/intake/whatsapp/manual', json={'texto': texto})
        body = resp.json()
        assert not body['proxima_acao'].startswith('Peça também')


def test_9b_datajud_com_erro_de_rede_tambem_gera_mensagem_rica_nao_so_generica(monkeypatch):
    """O outro lado do mesmo problema: falha de rede (não só vazio) também
    precisa disparar a mensagem rica quando há contexto documental forte."""
    async def fake_search_falha(self, search_type, search_key, **kwargs):
        raise Exception('Falha de rede simulada')
    monkeypatch.setattr('app.connectors.datajud.DataJudConnector.search', fake_search_falha)

    client = TestClient(app)
    resp = client.post('/api/intake/whatsapp/manual', json={'texto': TEXTO_OFICIO_REQUISITORIO})
    body = resp.json()
    assert 'TJSP' in body['proxima_acao'] or 'DEPRE' in body['proxima_acao']


# ---------------------------------------------------------------------------
# 10. Dossiê mostra CNJ base, sufixo, tipo documental, tribunal, próxima ação
# ---------------------------------------------------------------------------

def test_10_dossie_mostra_cnj_base_sufixo_tipo_documental(monkeypatch):
    _mock_datajud_vazio(monkeypatch)
    client = TestClient(app)
    resp = client.post('/api/intake/whatsapp/manual', json={'texto': TEXTO_OFICIO_REQUISITORIO})
    job_id = resp.json()['job_id']
    dossie = client.get(f'/api/bots/jobs/{job_id}/dossie')
    texto = dossie.text
    assert '0016114-59.2017.8.26.0053' in texto
    assert 'Ofício Requisitório' in texto


# ---------------------------------------------------------------------------
# Confirma que o caso já aprovado (TRF3, sem sufixo) continua funcionando
# ---------------------------------------------------------------------------

def test_regressao_cnj_sem_sufixo_continua_funcionando_em_diligencia():
    client = TestClient(app)
    resp = client.post('/api/diligencia', json={'input': '5000563-34.2022.4.03.6331'})
    body = resp.json()
    assert body['tipo_identificado'] == 'cnj'
