"""Testes v31e (CNJ com sufixo + ofício requisitório/precatório) e v31f
(processo referência + classe de documento). Casos reais reportados:
ação rescisória TJBA com processo referência, e ofício requisitório TJSP
com sufixo /01."""
import os

os.environ.setdefault('APP_LOGIN_PASSWORD', '')
os.environ.setdefault('INTERNAL_API_TOKEN', '')

from fastapi.testclient import TestClient

from app.main import app
from app.db import init_db
from app.services import whatsapp_intake
from app.utils.cnj import normalize_cnj, format_cnj, infer_tribunal_from_cnj, split_cnj_suffix

init_db()

TEXTO_ACAO_RESCISORIA = (
    'Número: 8045581-76.2026.8.05.0000\n'
    'Classe: AÇÃO RESCISÓRIA\n'
    'Órgão julgador: Segunda Câmara Cível\n'
    'Valor da causa: R$ 500.000,00\n'
    'Processo referência: 8000694-09.2025.8.05.0043\n'
    'Partes: Irmandade da Santa Casa de Misericórdia de Ilhéus e outros'
)

TEXTO_OFICIO_REQUISITORIO = (
    '0016114-59.2017.8.26.0053/01\n'
    'Ofício Requisitório nº 2149/2019\n'
    'Fazenda Pública do Estado de São Paulo\n'
    'Natureza: alimentar'
)


# ---------------------------------------------------------------------------
# v31e — CNJ com sufixo
# ---------------------------------------------------------------------------

def test_a_cnj_com_sufixo_separa_base_e_sufixo():
    base, sufixo = split_cnj_suffix('0016114-59.2017.8.26.0053/01')
    assert normalize_cnj(base) == '00161145920178260053'
    assert sufixo == '01'


def test_b_datajud_e_consultado_com_cnj_base(monkeypatch):
    from app.connectors.datajud import DataJudConnector
    chamadas = []

    async def fake_search_by_cnj(self, cnj, tribunals=None, max_results=50):
        chamadas.append(cnj)
        return []

    monkeypatch.setattr(DataJudConnector, 'search_by_cnj', fake_search_by_cnj)
    client = TestClient(app)
    client.post('/api/bots/run', json={'input': '0016114-59.2017.8.26.0053/01'})
    # a busca deve ter usado só os 20 digitos do CNJ base, nunca o sufixo colado
    assert all(len(c) == 20 for c in chamadas if c)


def test_c_tribunal_inferido_e_tjsp_mesmo_com_sufixo():
    assert infer_tribunal_from_cnj('0016114-59.2017.8.26.0053/01') == 'TJSP'


def test_d_oficio_requisitorio_e_identificado():
    r = whatsapp_intake.processar_mensagem(TEXTO_OFICIO_REQUISITORIO)
    assert r['eh_requisitorio_ou_precatorio'] is True
    assert r['classe_documento'] == 'Ofício Requisitório'


def test_e_datajud_vazio_recomenda_tjsp_depre_nao_erro_generico():
    client = TestClient(app)
    resp = client.post('/api/intake/whatsapp/manual', json={'texto': TEXTO_OFICIO_REQUISITORIO})
    body = resp.json()
    assert 'DEPRE' in body['proxima_acao']
    assert 'TJSP' in body['proxima_acao']
    assert 'não encontramos' not in body['proxima_acao'].lower()


def test_f_resultado_visual_mostra_cnj_base_sufixo_tribunal_tipo():
    r = whatsapp_intake.processar_mensagem(TEXTO_OFICIO_REQUISITORIO)
    p = r['processos_detectados'][0]
    assert p['cnj_normalizado'] == '0016114-59.2017.8.26.0053'
    assert p['sufixo'] == '01'
    assert p['tribunal_provavel'] == 'TJSP'
    assert r['eh_requisitorio_ou_precatorio'] is True


# ---------------------------------------------------------------------------
# v31f — processo referência, classe, valor, ação rescisória
# ---------------------------------------------------------------------------

def test_a_extrai_processo_principal():
    r = whatsapp_intake.processar_mensagem(TEXTO_ACAO_RESCISORIA)
    assert r['processos_detectados'][0]['cnj_normalizado'] == '8045581-76.2026.8.05.0000'


def test_b_extrai_processo_referencia():
    r = whatsapp_intake.processar_mensagem(TEXTO_ACAO_RESCISORIA)
    assert r['processo_referencia']['cnj_normalizado'] == '8000694-09.2025.8.05.0043'


def test_c_ambos_inferem_tjba():
    r = whatsapp_intake.processar_mensagem(TEXTO_ACAO_RESCISORIA)
    assert r['processos_detectados'][0]['tribunal_provavel'] == 'TJBA'
    assert r['processo_referencia']['tribunal_provavel'] == 'TJBA'


def test_d_classe_acao_rescisoria_detectada():
    r = whatsapp_intake.processar_mensagem(TEXTO_ACAO_RESCISORIA)
    assert r['classe_documento'] == 'Ação Rescisória'


def test_e_valor_da_causa_extraido():
    r = whatsapp_intake.processar_mensagem(TEXTO_ACAO_RESCISORIA)
    assert r['valor_causa'] == '500.000,00'


def test_f_se_datajud_vazio_e_tem_referencia_consulta_tambem_a_referencia(monkeypatch):
    async def fake_search(self, search_type, search_key, **kwargs):
        return []
    monkeypatch.setattr('app.connectors.datajud.DataJudConnector.search', fake_search)

    client = TestClient(app)
    resp = client.post('/api/intake/whatsapp/manual', json={'texto': TEXTO_ACAO_RESCISORIA})
    body = resp.json()
    assert body['job_id'] is not None
    assert body['job_id_referencia'] is not None
    assert body['job_id'] != body['job_id_referencia']


def test_g_resultado_visual_nao_diz_apenas_nao_encontrado():
    client = TestClient(app)
    resp = client.post('/api/intake/whatsapp/manual', json={'texto': TEXTO_ACAO_RESCISORIA})
    body = resp.json()
    assert 'ação rescisória' in body['proxima_acao'].lower()
    assert 'processo referência' in body['proxima_acao'].lower() or 'processo  referência' in body['proxima_acao'].lower()
    assert body['proxima_acao'].strip().lower() != 'não encontramos esse processo no datajud.'


def test_h_dossie_mostra_processo_principal_referencia_classe_valor():
    client = TestClient(app)
    resp = client.post('/api/intake/whatsapp/manual', json={'texto': TEXTO_ACAO_RESCISORIA})
    job_id = resp.json()['job_id']
    dossie = client.get(f'/api/bots/jobs/{job_id}/dossie')
    texto = dossie.text
    assert 'Ação Rescisória' in texto
    assert '8000694-09.2025.8.05.0043' in texto
    assert '500.000,00' in texto


def test_i_resposta_sugerida_menciona_acao_rescisoria_e_processo_referencia():
    r = whatsapp_intake.processar_mensagem(TEXTO_ACAO_RESCISORIA)
    resposta = whatsapp_intake.gerar_resposta_sugerida(r)
    assert 'ação rescisória' in resposta.lower()
    assert '8000694-09.2025.8.05.0043' in resposta


# ---------------------------------------------------------------------------
# Robustez: CNJ com sufixo continua reconhecido pelo extrator do intake
# (achado real: o formato de retorno mudou de lista de strings pra lista
# de dicts, e o contador de 20 dígitos quebrava com o sufixo colado)
# ---------------------------------------------------------------------------

def test_extrai_cnj_candidatos_com_sufixo_nao_quebra_contagem_de_digitos():
    candidatos = whatsapp_intake.extrair_cnj_candidatos('Processo 0016114-59.2017.8.26.0053/01 em andamento.')
    assert len(candidatos) == 1
    assert candidatos[0]['cnj'] == '00161145920178260053'
    assert candidatos[0]['sufixo'] == '01'


def test_cnj_sem_sufixo_continua_funcionando_normalmente():
    candidatos = whatsapp_intake.extrair_cnj_candidatos('Processo 5000563-34.2022.4.03.6331 em andamento.')
    assert len(candidatos) == 1
    assert candidatos[0]['sufixo'] is None


def test_mascaramento_de_cpf_continua_funcionando_com_cnj_de_sufixo():
    """Garante que o fix do formato de retorno não quebrou a proteção
    contra mascarar pedaço do CNJ (bug corrigido na v31b)."""
    r = whatsapp_intake.mascarar_documentos_no_texto('Processo 0016114-59.2017.8.26.0053/01. CPF 123.456.789-09.')
    assert '0016114-59.2017.8.26.0053/01' in r
    assert '123.***.***-09' in r
    assert '123.456.789-09' not in r
