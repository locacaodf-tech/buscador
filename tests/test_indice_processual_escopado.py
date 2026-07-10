"""Índice processual pessoal — escopado a ações contra ente público
(Estado/Município/União/INSS/Fazenda) com sinal de interesse (sentença,
trânsito em julgado, RPV, precatório, cálculos homologados, SECAJ).
Construído DENTRO do codebase real deste projeto (não a partir do ZIP de
proveniência duvidosa) — reaproveita o motor de sinais e o OpportunityLead
já existentes, sem duplicar arquitetura."""
import os

os.environ.setdefault('APP_LOGIN_PASSWORD', '')
os.environ.setdefault('INTERNAL_API_TOKEN', '')

from fastapi.testclient import TestClient

from app.main import app
from app.db import init_db, SessionLocal

init_db()

TEXTO_CASO_REAL = (
    'Processo: 1234567-89.2026.8.09.0128\n'
    'Autor: Ana Cristina Pereira dos Santos, CPF 111.222.333-96\n'
    'Réu: Estado de Goiás\n'
    'Assunto: cobrança comum, sentença proferida'
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
# Escopo: só indexa ação contra ente público OU com sinal — nunca genérico
# ---------------------------------------------------------------------------

def test_escopo_indexa_acao_contra_ente_publico_com_sentenca():
    _limpar()
    client = TestClient(app)
    resp = client.post('/api/watchers/import-publications', json={'texto_colado': TEXTO_CASO_REAL, 'tribunal': 'TJGO'})
    assert resp.json()['total_leads_created'] == 1


def test_escopo_nao_indexa_publicacao_generica_sem_ente_publico_nem_sinal():
    _limpar()
    client = TestClient(app)
    resp = client.post('/api/watchers/import-publications', json={
        'texto_colado': 'Processo entre particulares sobre contrato de aluguel, vista às partes para manifestação.',
        'tribunal': 'TJGO',
    })
    assert resp.json()['total_leads_created'] == 0
    assert len(client.get('/api/leads').json()) == 0


def test_secaj_e_reconhecido_como_sinal():
    from app.watchers.precatorio_signal_engine import classificar_publicacao
    r = classificar_publicacao('Autos remetidos ao SECAJ para elaboração de cálculos.')
    assert r['signal_type'] == 'calculo_homologado'


def test_sentenca_generica_e_reconhecida_como_sinal():
    from app.watchers.precatorio_signal_engine import classificar_publicacao
    r = classificar_publicacao('Julgo procedente o pedido inicial.')
    assert r['signal_type'] == 'sentenca_proferida'


# ---------------------------------------------------------------------------
# Extração de credor sem vazar fragmento de CPF no nome
# ---------------------------------------------------------------------------

def test_extrai_credor_sem_vazar_cpf_no_nome():
    from app.services.whatsapp_intake import extrair_credor
    r = extrair_credor(TEXTO_CASO_REAL)
    assert r['nome'] == 'Ana Cristina Pereira dos Santos'
    assert '111' not in r['nome']
    assert r['cpf'] == '11122233396'


# ---------------------------------------------------------------------------
# Busca por nome
# ---------------------------------------------------------------------------

def test_busca_por_nome_encontra():
    _limpar()
    client = TestClient(app)
    client.post('/api/watchers/import-publications', json={'texto_colado': TEXTO_CASO_REAL, 'tribunal': 'TJGO'})
    resultados = client.get('/api/leads/buscar', params={'nome': 'Ana Cristina'}).json()
    assert len(resultados) == 1
    assert resultados[0]['normalized_cnj'] == '1234567-89.2026.8.09.0128'


# ---------------------------------------------------------------------------
# Busca por CPF via hash — nunca em claro
# ---------------------------------------------------------------------------

def test_busca_por_cpf_encontra_via_hash():
    _limpar()
    client = TestClient(app)
    client.post('/api/watchers/import-publications', json={'texto_colado': TEXTO_CASO_REAL, 'tribunal': 'TJGO'})
    resultados = client.get('/api/leads/buscar', params={'cpf': '111.222.333-96'}).json()
    assert len(resultados) == 1
    assert resultados[0]['creditor_document_masked'] == '111.***.***-96'


def test_cpf_nunca_aparece_em_claro_em_nenhuma_resposta():
    _limpar()
    client = TestClient(app)
    resp = client.post('/api/watchers/import-publications', json={'texto_colado': TEXTO_CASO_REAL, 'tribunal': 'TJGO'})
    lead_id = client.get('/api/leads').json()[0]['id']
    for r in [
        client.get('/api/leads'),
        client.get(f'/api/leads/{lead_id}'),
        client.get('/api/leads/buscar', params={'nome': 'Ana'}),
        client.get(f'/api/leads/{lead_id}/dossie'),
        client.get('/api/leads/export.csv'),
    ]:
        assert '111.222.333-96' not in r.text
        assert '11122233396' not in r.text


# ---------------------------------------------------------------------------
# Busca por CNJ
# ---------------------------------------------------------------------------

def test_busca_por_cnj_encontra():
    _limpar()
    client = TestClient(app)
    client.post('/api/watchers/import-publications', json={'texto_colado': TEXTO_CASO_REAL, 'tribunal': 'TJGO'})
    resultados = client.get('/api/leads/buscar', params={'cnj': '1234567-89.2026.8.09.0128'}).json()
    assert len(resultados) == 1


# ---------------------------------------------------------------------------
# Salt padrão gera aviso
# ---------------------------------------------------------------------------

def test_salt_padrao_gera_aviso_no_status():
    client = TestClient(app)
    status = client.get('/api/watchers/status').json()
    assert 'indice_processual' in status
    assert status['indice_processual']['usando_salt_padrao'] is True
    assert 'atenção' in status['indice_processual']['aviso'].lower()


def test_salt_configurado_nao_gera_aviso(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv('INDICE_CPF_HASH_SALT', 'um-salt-de-producao-real-e-secreto')
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        status = client.get('/api/watchers/status').json()
        assert status['indice_processual']['usando_salt_padrao'] is False
        assert status['indice_processual']['aviso'] is None
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Remoção soft (padrão) vs hard
# ---------------------------------------------------------------------------

def test_remocao_soft_tira_da_busca_mas_preserva_dados():
    _limpar()
    client = TestClient(app)
    client.post('/api/watchers/import-publications', json={'texto_colado': TEXTO_CASO_REAL, 'tribunal': 'TJGO'})
    lead_id = client.get('/api/leads').json()[0]['id']
    resp = client.post(f'/api/leads/{lead_id}/remover')
    assert resp.json()['hard'] is False
    assert client.get('/api/leads/buscar', params={'nome': 'Ana Cristina'}).json() == []
    # dado ainda existe internamente (acessível direto por id, se necessário reverter)
    lead = client.get(f'/api/leads/{lead_id}').json()
    assert lead['creditor_name'] == 'Ana Cristina Pereira dos Santos'


def test_remocao_hard_limpa_documentos_hash_e_nome():
    _limpar()
    client = TestClient(app)
    client.post('/api/watchers/import-publications', json={'texto_colado': TEXTO_CASO_REAL, 'tribunal': 'TJGO'})
    lead_id = client.get('/api/leads').json()[0]['id']
    resp = client.post(f'/api/leads/{lead_id}/remover', params={'hard': 'true'})
    assert resp.json()['hard'] is True

    from app.models import OpportunityLead
    db = SessionLocal()
    lead = db.query(OpportunityLead).filter(OpportunityLead.id == lead_id).first()
    assert lead.creditor_name is None
    assert lead.creditor_document_hash is None
    assert lead.creditor_document_masked is None
    assert lead.publication_text == '[removido a pedido]'
    db.close()


def test_busca_por_cpf_nao_funciona_depois_do_hard_remove():
    _limpar()
    client = TestClient(app)
    client.post('/api/watchers/import-publications', json={'texto_colado': TEXTO_CASO_REAL, 'tribunal': 'TJGO'})
    lead_id = client.get('/api/leads').json()[0]['id']
    client.post(f'/api/leads/{lead_id}/remover', params={'hard': 'true'})
    resultados = client.get('/api/leads/buscar', params={'cpf': '111.222.333-96'}).json()
    assert resultados == []
