"""Testes do WhatsApp Intake Manual (v31). Cobre a lista pedida (A-P) na
medida do que é modo manual (sem OCR, sem webhook ativo — isso é
deliberado, testado como "preparado mas não ativado")."""
import os

os.environ.setdefault('APP_LOGIN_PASSWORD', '')
os.environ.setdefault('INTERNAL_API_TOKEN', '')

from fastapi.testclient import TestClient

from app.main import app
from app.db import init_db
from app.services import whatsapp_intake

init_db()


# ---------------------------------------------------------------------------
# A) "00007659720235070016" vira CNJ formatado
# ---------------------------------------------------------------------------

def test_normaliza_cnj_sem_pontuacao():
    r = whatsapp_intake.processar_mensagem('00007659720235070016')
    assert r['processos_detectados'][0]['cnj_normalizado'] == '0000765-97.2023.5.07.0016'


# ---------------------------------------------------------------------------
# B) "Fortaleza/CE" infere Ceará
# ---------------------------------------------------------------------------

def test_infere_ceara_a_partir_de_fortaleza():
    r = whatsapp_intake.processar_mensagem('Fortaleza/CE')
    assert r['uf'] == 'CE'
    assert r['cidade'] == 'Fortaleza'


# ---------------------------------------------------------------------------
# C) CNJ 2023.5.07 infere Justiça do Trabalho/TRT7
# ---------------------------------------------------------------------------

def test_cnj_trabalhista_infere_trt7():
    r = whatsapp_intake.processar_mensagem('00007659720235070016')
    p = r['processos_detectados'][0]
    assert p['segmento_nome'] == 'Justiça do Trabalho'
    assert p['tribunal_provavel'] == 'TRT7'
    assert p['ufs_cobertas'] == ['CE']


# ---------------------------------------------------------------------------
# D) "5000563.34.2022.4.03.6331" normaliza CNJ (separador com ponto, não hífen)
# ---------------------------------------------------------------------------

def test_normaliza_cnj_com_separador_de_ponto():
    r = whatsapp_intake.processar_mensagem('5000563.34.2022.4.03.6331')
    assert r['processos_detectados'][0]['cnj_normalizado'] == '5000563-34.2022.4.03.6331'


# ---------------------------------------------------------------------------
# E) CNJ 4.03 infere Justiça Federal/TRF3
# ---------------------------------------------------------------------------

def test_cnj_federal_infere_trf3():
    r = whatsapp_intake.processar_mensagem('5000563.34.2022.4.03.6331')
    p = r['processos_detectados'][0]
    assert p['segmento_nome'] == 'Justiça Federal'
    assert p['tribunal_provavel'] == 'TRF3'
    assert p['ufs_cobertas'] == ['MS', 'SP']


# ---------------------------------------------------------------------------
# F) CPF é extraído e mascarado
# ---------------------------------------------------------------------------

def test_cpf_extraido_e_mascarado():
    r = whatsapp_intake.processar_mensagem('Meu CPF é 123.456.789-09, obrigado')
    assert r['cpf'] == '12345678909'
    assert r['cpf_mascarado'] == '123.***.***-09'
    assert '789' not in r['cpf_mascarado']  # miolo do CPF nunca aparece mascarado


# ---------------------------------------------------------------------------
# G) Nome é extraído quando vem próximo de "nome"
# ---------------------------------------------------------------------------

def test_nome_extraido_proximo_da_palavra_nome():
    r = whatsapp_intake.processar_mensagem('Nome Julio Cesar Pereira, aguardo retorno')
    assert r['nome'] == 'Julio Cesar Pereira'


# ---------------------------------------------------------------------------
# H) Ente "INSS" é extraído
# ---------------------------------------------------------------------------

def test_ente_devedor_inss_extraido():
    r = whatsapp_intake.processar_mensagem('É contra o INSS')
    assert r['ente_devedor'] == 'INSS'


# ---------------------------------------------------------------------------
# I-L) Intake cria Lead, WhatsAppMessage, IntakeCase, aciona BotJob
# ---------------------------------------------------------------------------

def test_intake_cria_lead_message_case_e_aciona_job(monkeypatch):
    async def fake_search(self, search_type, search_key, **kwargs):
        return [{'numero_processo': search_key, 'tribunal': 'TRT7', 'classe': 'Teste', 'precatorio_score': 0}]
    monkeypatch.setattr('app.connectors.datajud.DataJudConnector.search', fake_search)

    client = TestClient(app)
    resp = client.post('/api/intake/whatsapp/manual', json={'texto': 'O número 00007659720235070016. Fortaleza/CE.', 'telefone': '5585999990000'})
    assert resp.status_code == 200
    body = resp.json()
    assert body['lead_id']
    assert body['case_id']
    assert body['job_id']  # BotJob acionado, já que achou CNJ
    assert body['evidence_id']

    from app.db import SessionLocal
    from app.models import Lead, WhatsAppMessage, IntakeCase
    db = SessionLocal()
    try:
        assert db.query(Lead).filter(Lead.id == body['lead_id']).first() is not None
        assert db.query(WhatsAppMessage).filter(WhatsAppMessage.lead_id == body['lead_id']).count() >= 1
        assert db.query(IntakeCase).filter(IntakeCase.id == body['case_id']).first() is not None
    finally:
        db.close()


def test_dados_extraidos_nunca_expoe_cpf_cnpj_em_claro():
    client = TestClient(app)
    resp = client.post('/api/intake/whatsapp/manual', json={'texto': 'CPF 123.456.789-09, nome Julio'})
    texto_resposta = resp.text
    assert '12345678909' not in texto_resposta
    assert '123.456.789-09' not in texto_resposta
    assert '123.***.***-09' in texto_resposta  # mascarado, isso sim pode aparecer


# ---------------------------------------------------------------------------
# M) Divergência TRF1/Pará vs número 4.03 gera alerta
# ---------------------------------------------------------------------------

def test_divergencia_para_trf1_vs_trf3():
    r = whatsapp_intake.processar_mensagem('Número 5000563.34.2022.4.03.6331. Corre no TRF1, no Pará (PA)?')
    assert len(r['divergencias']) == 1
    assert 'PA' in r['divergencias'][0]
    assert 'TRF3' in r['divergencias'][0]


def test_divergencia_com_nome_de_estado_por_extenso_sem_sigla():
    """Achado real: mensagem real do cliente às vezes cita só o nome do
    estado ('Pará'), sem a sigla de 2 letras — precisa reconhecer isso
    também, não só 'PA' isolado."""
    r = whatsapp_intake.processar_mensagem('Número do processo 5000563.34.2022.4.03.6331. Corre no TRF1, no Para?')
    assert r['uf'] == 'PA'
    assert len(r['divergencias']) == 1


def test_mato_grosso_do_sul_nao_e_confundido_com_mato_grosso():
    r_ms = whatsapp_intake.processar_mensagem('processo é de Mato Grosso do Sul')
    assert r_ms['uf'] == 'MS'
    r_mt = whatsapp_intake.processar_mensagem('processo é do Mato Grosso mesmo')
    assert r_mt['uf'] == 'MT'


def test_sem_mencionar_uf_divergente_nao_gera_alerta_falso():
    r = whatsapp_intake.processar_mensagem('Número do processo 5000563.34.2022.4.03.6331. INSS. CPF 123.456.789-09. Nome Julio Cesar Pereira.')
    assert r['divergencias'] == []


# ---------------------------------------------------------------------------
# N) Resposta sugerida ao cliente é gerada
# ---------------------------------------------------------------------------

def test_resposta_sugerida_menciona_cnj_e_tribunal():
    r = whatsapp_intake.processar_mensagem('00007659720235070016. Fortaleza/CE.')
    resposta = whatsapp_intake.gerar_resposta_sugerida(r)
    assert '0000765-97.2023.5.07.0016' in resposta
    assert 'TRT7' in resposta


def test_resposta_sugerida_pede_dado_faltante_quando_nao_ha_processo():
    r = whatsapp_intake.processar_mensagem('Oi, tudo bem?')
    resposta = whatsapp_intake.gerar_resposta_sugerida(r)
    assert 'poderia nos enviar' in resposta.lower()


# ---------------------------------------------------------------------------
# O) Print sem OCR salva evidência e pede texto manual
# ---------------------------------------------------------------------------

def test_screenshot_sem_ocr_salva_evidencia_e_pede_texto():
    client = TestClient(app)
    resp = client.post(
        '/api/intake/whatsapp/screenshot',
        data={'telefone': '5585999990000'},
        files={'arquivo': ('print.png', b'conteudo de imagem fake', 'image/png')},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body['ocr_disponivel'] is False
    assert 'cole' in body['proxima_acao'].lower() or 'texto' in body['proxima_acao'].lower()
    assert body['lead_id']


# ---------------------------------------------------------------------------
# P) webhook WhatsApp aceita payload de teste (preparado, não ativo)
# ---------------------------------------------------------------------------

def test_webhook_get_devolve_403_sem_token_configurado():
    client = TestClient(app)
    resp = client.get('/api/whatsapp/webhook')
    assert resp.status_code == 403


def test_webhook_get_com_token_certo_devolve_challenge(monkeypatch):
    """Usa env var + cache_clear (não monkeypatch direto no objeto
    settings) — achado real: outros testes (PortalBot) chamam
    get_settings.cache_clear() em algum momento da suíte completa, o que
    dessincroniza qualquer referência direta ao objeto settings antigo do
    que get_settings() de fato devolve depois disso. Env var é a única
    forma imune à ordem de execução dos outros arquivos de teste."""
    from app.config import get_settings
    monkeypatch.setenv('WHATSAPP_VERIFY_TOKEN', 'meu-token-teste')
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        resp = client.get('/api/whatsapp/webhook', params={'hub.verify_token': 'meu-token-teste', 'hub.challenge': '12345'})
        assert resp.status_code == 200
        assert resp.json() == 12345
    finally:
        get_settings.cache_clear()


def test_webhook_post_devolve_501_nao_ativado():
    client = TestClient(app)
    resp = client.post('/api/whatsapp/webhook', json={'entry': []})
    assert resp.status_code == 501


# ---------------------------------------------------------------------------
# Extras: robustez da extração
# ---------------------------------------------------------------------------

def test_cpf_nao_e_extraido_de_dentro_do_cnj():
    """Achado real testando: um CNJ de 20 dígitos contém, por coincidência,
    uma sequência de 11 dígitos que passaria no regex solto de CPF."""
    r = whatsapp_intake.processar_mensagem('00007659720235070016')
    assert r['cpf'] is None


def test_dados_faltantes_lista_o_que_realmente_falta():
    r = whatsapp_intake.processar_mensagem('oi')
    assert 'Número do processo/CNJ' in r['dados_faltantes']
    assert 'CPF ou CNPJ' in r['dados_faltantes']
    assert 'Nome completo' in r['dados_faltantes']
