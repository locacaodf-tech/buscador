"""Testes do Motor Operacional de Diligência (v28) — cobre a lista pedida:
CPF/CNPJ sem provider, nome com/sem STJ, CNJ roteado pro DataJud, DataJud
falhando sem quebrar, sequencial STJ com/sem XLSX, precatório/RPV gerando
plano, certidão gerando plano, resposta sempre com próxima ação, e o
endpoint /api/diligencia funcionando ponta a ponta."""
import asyncio
import io
import os

os.environ.setdefault('APP_LOGIN_PASSWORD', '')
os.environ.setdefault('INTERNAL_API_TOKEN', '')

from fastapi.testclient import TestClient

from app.main import app
from app.db import init_db
from app.services import diligencia_engine
from app.services import stj_uploads

init_db()


def _client_com_stj_isolado(tmp_path, monkeypatch):
    isolado = tmp_path / 'stj_uploads'
    monkeypatch.setattr(stj_uploads, 'UPLOAD_DIR', isolado)
    monkeypatch.setattr(stj_uploads, 'upload_dir', lambda: isolado)
    return TestClient(app)


def _xlsx_com_credor() -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'PRCs'
    ws.append(['Relação de Precatórios Expedidos - STJ'])
    ws.append([])
    ws.append(['Ordem', 'Classe', 'Sequencial', 'Processo', 'Credor/Beneficiário', 'Valor', 'Previsão'])
    ws.append([1, 'PRC', 15547, '0506671-51.2025.3.00.0000', 'MARIA DA SILVA SOUZA', '1.708.161,78', 'fevereiro/2026'])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 1-2. CPF/CNPJ sem provider comercial
# ---------------------------------------------------------------------------

def test_cpf_sem_provider_orienta_sem_fingir_resultado(monkeypatch):
    r = asyncio.run(diligencia_engine.run_diligencia('721.377.971-00'))
    assert r['tipo_identificado'] == 'cpf'
    assert r['valor_normalizado'] == '72137797100'
    assert 'provider comercial' in r['proxima_acao_recomendada'].lower()


def test_cnpj_sem_provider_orienta_sem_fingir_resultado(monkeypatch):
    r = asyncio.run(diligencia_engine.run_diligencia('00.000.000/0001-91'))
    assert r['tipo_identificado'] == 'cnpj'
    assert 'provider comercial' in r['proxima_acao_recomendada'].lower()


# ---------------------------------------------------------------------------
# 3. Nome sem STJ carregado, com orientação (não finge que pesquisou)
# ---------------------------------------------------------------------------

def test_nome_sem_stj_carregado_orienta_upload(tmp_path, monkeypatch):
    isolado = tmp_path / 'stj_uploads'
    monkeypatch.setattr(stj_uploads, 'UPLOAD_DIR', isolado)
    monkeypatch.setattr(stj_uploads, 'upload_dir', lambda: isolado)

    r = asyncio.run(diligencia_engine.run_diligencia('Maria da Silva'))
    assert r['tipo_identificado'] == 'name'
    assert any('xlsx' in p.lower() for p in r['pendencias'])
    assert 'stj' in r['proxima_acao_recomendada'].lower()


# ---------------------------------------------------------------------------
# 4. Nome com STJ XLSX carregado — encontra de verdade
# ---------------------------------------------------------------------------

def test_nome_com_stj_carregado_encontra_registro_real(tmp_path, monkeypatch):
    client = _client_com_stj_isolado(tmp_path, monkeypatch)
    client.post('/api/stj-precatorios/upload-xlsx', files={'file': ('teste.xlsx', _xlsx_com_credor(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})

    resp = client.post('/api/diligencia', json={'input': 'maria da silva'})
    assert resp.status_code == 200
    body = resp.json()
    assert body['tipo_identificado'] == 'name'
    assert len(body['resultados_confirmados']) == 1
    assert body['resultados_confirmados'][0]['credor'] == 'MARIA DA SILVA SOUZA'
    assert body['resultados_confirmados'][0]['valor'] == 1708161.78


# ---------------------------------------------------------------------------
# 5-6. CNJ roteado pro DataJud, e DataJud falhando sem quebrar a diligência
# ---------------------------------------------------------------------------

def test_cnj_e_roteado_para_datajud(monkeypatch):
    chamado = {}

    async def fake_search(self, search_type, search_key, **kwargs):
        chamado['search_type'] = search_type
        chamado['search_key'] = search_key
        return [{'numero_processo': search_key, 'tribunal': 'TRF1', 'classe': 'Teste', 'precatorio_score': 0}]

    monkeypatch.setattr('app.connectors.datajud.DataJudConnector.search', fake_search)
    r = asyncio.run(diligencia_engine.run_diligencia('0032681-47.2017.4.01.3400'))
    assert r['tipo_identificado'] == 'cnj'
    assert chamado['search_type'] == 'cnj'
    assert any(e['nome'] == 'DataJud' for e in r['consultas_realizadas'])


def test_datajud_indisponivel_nao_quebra_a_diligencia(monkeypatch):
    from app.connectors.base import ConnectorError

    async def fake_search_falha(self, search_type, search_key, **kwargs):
        raise ConnectorError('Timeout de rede simulado')

    monkeypatch.setattr('app.connectors.datajud.DataJudConnector.search', fake_search_falha)
    r = asyncio.run(diligencia_engine.run_diligencia('0032681-47.2017.4.01.3400'))
    assert r['tipo_identificado'] == 'cnj'
    assert r['proxima_acao_recomendada']  # sempre tem próxima ação, mesmo em falha
    assert any(e['status'] == 'falhou' for e in r['consultas_realizadas'])


# ---------------------------------------------------------------------------
# 7-8. Sequencial STJ sem/com XLSX
# ---------------------------------------------------------------------------

def test_sequencial_stj_sem_xlsx_orienta_upload(tmp_path, monkeypatch):
    isolado = tmp_path / 'stj_uploads'
    monkeypatch.setattr(stj_uploads, 'UPLOAD_DIR', isolado)
    monkeypatch.setattr(stj_uploads, 'upload_dir', lambda: isolado)

    r = asyncio.run(diligencia_engine.run_diligencia('15547'))
    assert any('xlsx' in p.lower() for p in r['pendencias'])


def test_sequencial_stj_com_xlsx_encontra_registro(tmp_path, monkeypatch):
    client = _client_com_stj_isolado(tmp_path, monkeypatch)
    client.post('/api/stj-precatorios/upload-xlsx', files={'file': ('teste.xlsx', _xlsx_com_credor(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})

    resp = client.post('/api/diligencia', json={'input': '15547'})
    body = resp.json()
    assert len(body['resultados_confirmados']) == 1
    assert body['resultados_confirmados'][0]['sequencial'] == '15547'


# ---------------------------------------------------------------------------
# 9. Precatório/RPV com dados incompletos gerando plano
# ---------------------------------------------------------------------------

def test_precatorio_com_dados_incompletos_gera_plano():
    r = asyncio.run(diligencia_engine.run_diligencia('precatorio 99999'))
    assert r['tipo_identificado'] == 'precatorio_number'
    assert 'plano_precatorio' in r['raw_avancado']
    assert r['proxima_acao_recomendada']


# ---------------------------------------------------------------------------
# 10. Certidão gerando plano operacional
# ---------------------------------------------------------------------------

def test_objetivo_certidao_gera_plano_de_certidoes():
    r = asyncio.run(diligencia_engine.run_diligencia('72137797100', objetivo='certidao'))
    assert 'certidoes' in r['raw_avancado']
    # o plano nunca deve APRESENTAR "nada consta" como se fosse um resultado
    # real (o endpoint é só planejamento, nenhuma certidão é emitida aqui).
    assert r['raw_avancado']['certidoes'].get('note', '').startswith('Plano informativo')
    assert 'steps' in r['raw_avancado']['certidoes']


# ---------------------------------------------------------------------------
# 11. Resposta sempre contém próxima ação recomendada
# ---------------------------------------------------------------------------

def test_resposta_sempre_tem_proxima_acao():
    entradas = ['72137797100', 'Maria da Silva', '0032681-47.2017.4.01.3400', '15547', 'precatorio 123', 'texto qualquer sem padrao']
    for entrada in entradas:
        r = asyncio.run(diligencia_engine.run_diligencia(entrada))
        assert r['proxima_acao_recomendada'], f'faltou proxima_acao para: {entrada}'


# ---------------------------------------------------------------------------
# 12. Endpoint /api/diligencia funciona ponta a ponta (frontend chamaria isto)
# ---------------------------------------------------------------------------

def test_endpoint_diligencia_funciona_ponta_a_ponta():
    client = TestClient(app)
    resp = client.post('/api/diligencia', json={'input': '721.377.971-00'})
    assert resp.status_code == 200
    body = resp.json()
    assert body['tipo_identificado'] == 'cpf'
    assert 'resumo_humano' in body
    assert 'raw_avancado' in body


def test_endpoint_diligencia_aceita_objetivo_e_uf_tribunal():
    client = TestClient(app)
    resp = client.post('/api/diligencia', json={'input': 'precatorio 123', 'uf': 'DF', 'tribunal': 'TRF1', 'objetivo': 'completo'})
    assert resp.status_code == 200


def test_endpoint_diligencia_rejeita_objetivo_invalido():
    client = TestClient(app)
    resp = client.post('/api/diligencia', json={'input': 'teste', 'objetivo': 'invalido'})
    assert resp.status_code == 422
