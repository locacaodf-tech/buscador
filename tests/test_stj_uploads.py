import io
import os

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

os.environ.setdefault('APP_LOGIN_PASSWORD', '')
os.environ.setdefault('INTERNAL_API_TOKEN', '')

from app.main import app  # noqa: E402
from app.services import stj_uploads  # noqa: E402


def build_synthetic_stj_xlsx() -> bytes:
    """Mesma estrutura do print real (28/06/2026): ordem | classe |
    sequencial | processo | prioridade | valor | previsão."""
    wb = Workbook()
    ws = wb.active
    ws.title = 'PRCs Alimentar'
    ws.append(['Relação de Precatórios Expedidos - STJ'])
    ws.append([])
    ws.append(['Ordem', 'Classe', 'Sequencial', 'Processo', 'Prioridade', 'Valor', 'Previsão de pagamento'])
    ws.append([143, 'PRC', 15547, '0506671-51.2025.3.00.0000', 'Idoso', '1.708.161,78', 'fevereiro/2026'])
    ws.append([144, 'PRC', 15548, '0506675-88.2025.3.00.0000', 'Idoso', '1.154.779,51', 'fevereiro/2026'])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Isola cada teste numa pasta de upload própria, sem sujar data/ real do projeto.
    # Precisa travar tanto UPLOAD_DIR (fallback) quanto upload_dir() (que agora
    # prioriza STJ_UPLOAD_DIR do settings) — senão, com a variável configurada
    # no .env, os testes vazam pra pasta real e se contaminam entre si.
    isolated_dir = tmp_path / 'stj_uploads'
    monkeypatch.setattr(stj_uploads, 'UPLOAD_DIR', isolated_dir)
    monkeypatch.setattr(stj_uploads, 'upload_dir', lambda: isolated_dir)
    return TestClient(app)


def test_busca_sem_upload_diz_arquivo_nao_carregado(client):
    resp = client.post('/api/stj-precatorios/search', json={'search_type': 'sequencial', 'search_key': '15547'})
    assert resp.status_code == 200
    data = resp.json()
    assert data['status'] == 'not_loaded'
    assert data['message'] == 'Arquivo oficial do STJ ainda não carregado.'
    assert data['results'] == []
    assert data['total'] == 0


def test_upload_extensao_invalida_e_rejeitado(client):
    resp = client.post(
        '/api/stj-precatorios/upload-xlsx',
        files={'file': ('arquivo.txt', b'nao e xlsx', 'text/plain')},
    )
    assert resp.status_code == 400


def test_upload_relata_abas_campos_e_linhas(client):
    content = build_synthetic_stj_xlsx()
    resp = client.post(
        '/api/stj-precatorios/upload-xlsx',
        files={'file': ('PRCs-proposta-2027.xlsx', content, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data['status'] == 'uploaded'
    assert data['arquivo_original'] == 'PRCs-proposta-2027.xlsx'
    assert 'uploaded_at' in data
    assert len(data['abas']) == 1
    aba = data['abas'][0]
    assert aba['aba'] == 'PRCs Alimentar'
    assert aba['registros_lidos'] == 2
    assert 'sequencial' in aba['campos_detectados']
    assert 'numero_processo' in aba['campos_detectados']
    assert 'valor' in aba['campos_detectados']


def test_upload_depois_busca_retorna_linha_correta_do_arquivo_real(client):
    content = build_synthetic_stj_xlsx()
    up = client.post(
        '/api/stj-precatorios/upload-xlsx',
        files={'file': ('Precatorios-Expedidos-Alimentar.xlsm', content, 'application/octet-stream')},
    )
    assert up.status_code == 200

    resp = client.post('/api/stj-precatorios/search', json={'search_type': 'sequencial', 'search_key': '15547'})
    assert resp.status_code == 200
    data = resp.json()
    assert data['status'] == 'completed'
    assert data['total'] == 1
    rec = data['results'][0]

    # O valor tem que ser o do arquivo carregado (1.708.161,78), nunca os
    # R$ 187.452,36 fictícios do incidente original.
    assert rec['valor'] == pytest.approx(1708161.78)
    assert rec['sequencial'] == '15547'
    assert rec['classe'] == 'PRC'
    assert rec['numero_processo'] == '0506671-51.2025.3.00.0000'
    assert rec['previsao_pagamento'] == 'fevereiro/2026'

    # Metadados de proveniência obrigatórios (fonte + arquivo + data + linha)
    assert rec['fonte'] == 'STJ - XLSX oficial carregado manualmente'
    assert rec['arquivo_original'] == 'Precatorios-Expedidos-Alimentar.xlsm'
    assert 'uploaded_at' in rec
    assert 'consultado_em' in rec
    assert rec['aba'] == 'PRCs Alimentar'
    assert rec['linha_arquivo'] == 4  # linha 1=título, 2=vazia, 3=cabeçalho, 4=primeira linha de dado


def test_busca_por_processo_cnj_no_arquivo_carregado(client):
    content = build_synthetic_stj_xlsx()
    client.post('/api/stj-precatorios/upload-xlsx', files={'file': ('teste.xlsx', content, 'application/octet-stream')})
    resp = client.post('/api/stj-precatorios/search', json={'search_type': 'cnj', 'search_key': '0506671-51.2025.3.00.0000'})
    data = resp.json()
    assert data['total'] == 1
    assert data['results'][0]['sequencial'] == '15547'


def test_busca_sequencial_inexistente_no_arquivo_real_retorna_vazio(client):
    content = build_synthetic_stj_xlsx()
    client.post('/api/stj-precatorios/upload-xlsx', files={'file': ('teste.xlsx', content, 'application/octet-stream')})
    resp = client.post('/api/stj-precatorios/search', json={'search_type': 'sequencial', 'search_key': '00000'})
    data = resp.json()
    assert data['status'] == 'completed'
    assert data['total'] == 0
    assert data['results'] == []


def test_valores_ficticios_do_incidente_nunca_aparecem_apos_upload_real(client):
    content = build_synthetic_stj_xlsx()
    client.post('/api/stj-precatorios/upload-xlsx', files={'file': ('teste.xlsx', content, 'application/octet-stream')})
    resp = client.post('/api/stj-precatorios/search', json={'search_type': 'sequencial', 'search_key': '15547'})
    dump = resp.text
    for proibido in ['OF-2027/004521', 'PRC-2027/0089341', '187452.36', '187.452', 'Fulano de Tal']:
        assert proibido not in dump, f'valor fictício do incidente vazou: {proibido}'


def test_filtro_ano_orcamento_no_upload(client):
    content = build_synthetic_stj_xlsx()
    client.post('/api/stj-precatorios/upload-xlsx', files={'file': ('PRCs-proposta-2027.xlsx', content, 'application/octet-stream')})
    # PRCs-proposta-2027.xlsx -> infer_file_metadata detecta ano_orcamento=2027
    certo = client.post('/api/stj-precatorios/search', json={'search_type': 'sequencial', 'search_key': '15547', 'ano_orcamento': 2027})
    assert certo.json()['total'] == 1
    errado = client.post('/api/stj-precatorios/search', json={'search_type': 'sequencial', 'search_key': '15547', 'ano_orcamento': 2030})
    assert errado.json()['total'] == 0
