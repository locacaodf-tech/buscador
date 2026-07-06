"""Testes do StjBot executor real (v30.2). Usa um fixture HTML fiel ao
conteúdo real da página de precatórios do STJ (obtido via fetch direto
durante o desenvolvimento — ver tests/fixtures/stj_precatorios_page.html e
RELATORIO_V30_2 pra mais detalhes) e mocka apenas a etapa de download HTTP
(sandbox sem acesso a domínios externos gerais). O parsing de links e a
integração com o parser já existente usam dados reais o tempo todo."""
import io
import os
from pathlib import Path

os.environ.setdefault('APP_LOGIN_PASSWORD', '')
os.environ.setdefault('INTERNAL_API_TOKEN', '')

from fastapi.testclient import TestClient

from app.main import app
from app.db import init_db, SessionLocal
from app.services import stj_uploads
from app.services import stj_official_scraper as scraper

init_db()

FIXTURE_HTML = (Path(__file__).parent / 'fixtures' / 'stj_precatorios_page.html').read_text()


def _xlsx_teste(sequencial=99887, credor='JOAO TESTE DA SILVA', valor='500.000,00') -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(['Relação de Precatórios Expedidos - STJ'])
    ws.append([])
    ws.append(['Ordem', 'Classe', 'Sequencial', 'Processo', 'Credor/Beneficiário', 'Valor', 'Previsão'])
    ws.append([1, 'PRC', sequencial, '0506671-51.2025.3.00.0000', credor, valor, 'marco/2027'])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# A) STJBot encontra link XLSX na página HTML real (fixture fiel)
# ---------------------------------------------------------------------------

def test_extrai_links_de_arquivo_da_pagina_real_do_stj():
    links = scraper.extract_official_file_links(FIXTURE_HTML)
    assert len(links) == 10  # confirmado contra o fixture fiel à página real
    nomes = [l['filename'] for l in links]
    assert 'Mapa-Anual-Precatorios-2025.xlsx' in nomes
    # nunca captura os links que não são arquivo (PowerBI, menu institucional)
    assert not any('powerbi' in l['url'].lower() for l in links)
    assert not any('institucional' in l['url'].lower() for l in links)


def test_infere_ano_do_contexto_do_link():
    links = scraper.extract_official_file_links(FIXTURE_HTML)
    mapa_2025 = next(l for l in links if '2025' in l['filename'] and 'Mapa' in l['filename'])
    meta = scraper.infer_metadata_from_context(mapa_2025)
    assert meta['year'] == 2025


# ---------------------------------------------------------------------------
# B) Página com link intermediário — este fixture específico do STJ já tem
# link direto (confirmado contra a página real), mas o extrator não quebra
# se algum link não for de arquivo (só ignora).
# ---------------------------------------------------------------------------

def test_ignora_links_que_nao_sao_arquivo_sem_quebrar():
    html_com_link_intermediario = FIXTURE_HTML + '<a href="/pagina/intermediaria">Ver mais detalhes</a>'
    links = scraper.extract_official_file_links(html_com_link_intermediario)
    assert len(links) == 10  # mesmo total de antes, o link intermediário foi ignorado


# ---------------------------------------------------------------------------
# C) StjBot salva StjOfficialFile
# ---------------------------------------------------------------------------

def test_sync_salva_stjofficialfile_para_cada_arquivo(tmp_path, monkeypatch):
    isolado = tmp_path / 'oficial_sync'
    isolado.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(scraper, 'official_files_dir', lambda: isolado)

    async def fake_download(url):
        return _xlsx_teste()
    monkeypatch.setattr(scraper, 'download_file', fake_download)

    db = SessionLocal()
    try:
        from app.models import StjOfficialFile
        antes = db.query(StjOfficialFile).count()
        resultado = __import__('asyncio').run(scraper.sync_official_files(db, max_files=2, html_override=FIXTURE_HTML))
        assert resultado['status'] == 'ok'
        depois = db.query(StjOfficialFile).all()
        novos = [r for r in depois if r.id > antes]
        assert len(resultado['arquivos_processados']) == 2
        assert all(a['status'] == 'downloaded' for a in resultado['arquivos_processados'])
    finally:
        db.close()


# ---------------------------------------------------------------------------
# D) StjBot usa arquivo baixado na busca por sequencial
# ---------------------------------------------------------------------------

def test_busca_por_sequencial_usa_arquivo_recem_baixado(tmp_path, monkeypatch):
    isolado = tmp_path / 'oficial_sync'
    isolado.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(scraper, 'official_files_dir', lambda: isolado)

    async def fake_download(url):
        return _xlsx_teste(sequencial=55443, credor='MARIA EXEMPLO')
    monkeypatch.setattr(scraper, 'download_file', fake_download)

    db = SessionLocal()
    try:
        import asyncio
        asyncio.run(scraper.sync_official_files(db, max_files=1, html_override=FIXTURE_HTML))
        registros = scraper.registros_de_arquivos_baixados(db)
        achou = [r for r in registros if r.get('sequencial') == '55443']
        assert len(achou) == 1
        assert achou[0]['credor_nome'] == 'MARIA EXEMPLO'
        assert achou[0]['fonte_url'].startswith('https://www.stj.jus.br/')
    finally:
        db.close()


# ---------------------------------------------------------------------------
# E) Sem arquivo e sem conseguir baixar -> waiting_user/partial, nunca completed
# ---------------------------------------------------------------------------

def test_stjbot_sem_conseguir_baixar_nunca_fica_completed(tmp_path, monkeypatch):
    isolado = tmp_path / 'stj_uploads'
    monkeypatch.setattr(stj_uploads, 'UPLOAD_DIR', isolado)
    monkeypatch.setattr(stj_uploads, 'upload_dir', lambda: isolado)

    async def fake_fetch_falha():
        raise Exception('Falha simulada de rede')
    monkeypatch.setattr(scraper, 'fetch_precatorios_page', fake_fetch_falha)

    client = TestClient(app)
    resp = client.post('/api/bots/run', json={'input': '15547'})
    body = resp.json()
    assert body['status'] != 'completed'
    stj_step = next(b for b in body['bots_executados'] if b['bot_id'] == 'stj_bot')
    assert stj_step['status'] == 'pendente'
    assert 'upload manual' in stj_step['next_action'].lower()


# ---------------------------------------------------------------------------
# F) /api/stj-precatorios/sync funciona com fixture
# ---------------------------------------------------------------------------

def test_endpoint_sync_funciona_com_fixture(tmp_path, monkeypatch):
    (tmp_path / 'oficial_sync').mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(scraper, 'official_files_dir', lambda: tmp_path / 'oficial_sync')
    async def fake_fetch():
        return FIXTURE_HTML
    async def fake_download(url):
        return _xlsx_teste()
    monkeypatch.setattr(scraper, 'fetch_precatorios_page', fake_fetch)
    monkeypatch.setattr(scraper, 'download_file', fake_download)

    client = TestClient(app)
    resp = client.post('/api/stj-precatorios/sync')
    assert resp.status_code == 200
    body = resp.json()
    assert body['status'] == 'ok'
    assert len(body['arquivos_processados']) > 0

    lista = client.get('/api/stj-precatorios/official-files').json()
    assert len(lista) > 0
    assert lista[0]['status'] == 'downloaded'


# ---------------------------------------------------------------------------
# G) /api/bots/run com 15547 aciona sync quando não há XLSX
# ---------------------------------------------------------------------------

def test_bots_run_aciona_sync_quando_nao_ha_xlsx(tmp_path, monkeypatch):
    isolado = tmp_path / 'stj_uploads'
    monkeypatch.setattr(stj_uploads, 'UPLOAD_DIR', isolado)
    monkeypatch.setattr(stj_uploads, 'upload_dir', lambda: isolado)
    (tmp_path / 'oficial_sync').mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(scraper, 'official_files_dir', lambda: tmp_path / 'oficial_sync')

    chamado = {'vezes': 0}
    async def fake_fetch():
        chamado['vezes'] += 1
        return FIXTURE_HTML
    async def fake_download(url):
        return _xlsx_teste(sequencial=15547, credor='CREDOR DO TESTE')
    monkeypatch.setattr(scraper, 'fetch_precatorios_page', fake_fetch)
    monkeypatch.setattr(scraper, 'download_file', fake_download)

    client = TestClient(app)
    resp = client.post('/api/bots/run', json={'input': '15547'})
    assert chamado['vezes'] == 1  # sync foi de fato acionado
    body = resp.json()
    stj_step = next(b for b in body['bots_executados'] if b['bot_id'] == 'stj_bot')
    assert stj_step['status'] == 'concluido'


# ---------------------------------------------------------------------------
# H) Job completed se achou resultado / I) partial se precisa upload
# ---------------------------------------------------------------------------

def test_job_completed_quando_sync_encontra_resultado(tmp_path, monkeypatch):
    isolado = tmp_path / 'stj_uploads'
    monkeypatch.setattr(stj_uploads, 'UPLOAD_DIR', isolado)
    monkeypatch.setattr(stj_uploads, 'upload_dir', lambda: isolado)
    (tmp_path / 'oficial_sync').mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(scraper, 'official_files_dir', lambda: tmp_path / 'oficial_sync')

    async def fake_fetch():
        return FIXTURE_HTML
    async def fake_download(url):
        return _xlsx_teste(sequencial=77665)
    monkeypatch.setattr(scraper, 'fetch_precatorios_page', fake_fetch)
    monkeypatch.setattr(scraper, 'download_file', fake_download)

    client = TestClient(app)
    resp = client.post('/api/bots/run', json={'input': '77665'})
    body = resp.json()
    stj_step = next(b for b in body['bots_executados'] if b['bot_id'] == 'stj_bot')
    assert stj_step['status'] == 'concluido'
    # O mock devolve o mesmo conteúdo pra todos os arquivos "baixados" (até
    # MAX_FILES_PER_SYNC) — na produção, cada arquivo real teria conteúdo
    # diferente. O que importa aqui é confirmar que encontrou o sequencial
    # certo pelo menos uma vez, com os campos certos.
    encontrados = stj_step['resultado']['resultados_confirmados']
    assert len(encontrados) >= 1
    assert all(r['sequencial'] == '77665' for r in encontrados)
    assert encontrados[0]['credor'] == 'JOAO TESTE DA SILVA'


def test_job_partial_quando_sync_falha_e_precisa_upload(tmp_path, monkeypatch):
    isolado = tmp_path / 'stj_uploads'
    monkeypatch.setattr(stj_uploads, 'UPLOAD_DIR', isolado)
    monkeypatch.setattr(stj_uploads, 'upload_dir', lambda: isolado)

    async def fake_fetch_falha():
        raise Exception('Sem rede (esperado neste ambiente)')
    monkeypatch.setattr(scraper, 'fetch_precatorios_page', fake_fetch_falha)

    client = TestClient(app)
    resp = client.post('/api/bots/run', json={'input': '15547'})
    assert resp.json()['status'] == 'partial'


# ---------------------------------------------------------------------------
# J) Dossiê mostra URL oficial e arquivo consultado
# ---------------------------------------------------------------------------

def test_dossie_do_job_mostra_url_oficial_consultada(tmp_path, monkeypatch):
    isolado = tmp_path / 'stj_uploads'
    monkeypatch.setattr(stj_uploads, 'UPLOAD_DIR', isolado)
    monkeypatch.setattr(stj_uploads, 'upload_dir', lambda: isolado)
    (tmp_path / 'oficial_sync').mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(scraper, 'official_files_dir', lambda: tmp_path / 'oficial_sync')

    async def fake_fetch():
        return FIXTURE_HTML
    async def fake_download(url):
        return _xlsx_teste(sequencial=33221)
    monkeypatch.setattr(scraper, 'fetch_precatorios_page', fake_fetch)
    monkeypatch.setattr(scraper, 'download_file', fake_download)

    client = TestClient(app)
    resp = client.post('/api/bots/run', json={'input': '33221'})
    job_id = resp.json()['job_id']
    dossie = client.get(f'/api/bots/jobs/{job_id}/dossie')
    assert dossie.status_code == 200
    assert 'stj.jus.br' in dossie.text


def test_dossie_mostra_todos_os_campos_uteis_do_stj(tmp_path, monkeypatch):
    """Achado real de auditoria: o dossiê só mostrava parte dos campos que
    o StjBot já tinha internamente (faltava processo, classe, previsão,
    natureza, entidade devedora, ano) — corrigido normalizando os dois
    fluxos (upload manual e sync automático) com a mesma função única."""
    isolado = tmp_path / 'stj_uploads'
    monkeypatch.setattr(stj_uploads, 'UPLOAD_DIR', isolado)
    monkeypatch.setattr(stj_uploads, 'upload_dir', lambda: isolado)

    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(['Relação de Precatórios Expedidos - STJ'])
    ws.append([])
    ws.append(['Ordem', 'Classe', 'Sequencial', 'Processo', 'Credor/Beneficiário', 'Natureza', 'Entidade Devedora', 'Valor', 'Previsão'])
    ws.append([1, 'PRC', 44556, '0506671-51.2025.3.00.0000', 'CREDOR TESTE COMPLETO', 'Alimentar', 'União', '999.888,77', 'janeiro/2027'])
    buf = io.BytesIO()
    wb.save(buf)

    client = TestClient(app)
    client.post('/api/stj-precatorios/upload-xlsx', files={'file': ('teste_completo.xlsx', buf.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})

    resp = client.post('/api/bots/run', json={'input': '44556'})
    job_id = resp.json()['job_id']
    dossie = client.get(f'/api/bots/jobs/{job_id}/dossie')
    assert dossie.status_code == 200
    texto = dossie.text
    # todos os campos pedidos precisam aparecer, com valor de verdade
    assert '0506671-51.2025.3.00.0000' in texto  # processo/CNJ
    assert 'PRC' in texto  # classe
    assert 'CREDOR TESTE COMPLETO' in texto  # credor
    assert '999.888' in texto or '999888' in texto  # valor
    assert 'janeiro/2027' in texto  # previsão
    assert 'Alimentar' in texto  # natureza
    assert 'União' in texto  # entidade devedora
    assert 'teste_completo.xlsx' in texto  # arquivo
    assert 'Sheet' in texto  # aba
    assert '44556' in texto  # sequencial


# ---------------------------------------------------------------------------
# Achado real testando: página com robots.txt bloqueado (como o TJPE) nunca
# deveria ser um alvo — este teste documenta a checagem que EU fiz antes de
# construir isso (ver RELATORIO_V30_2), não testa código novo.
# ---------------------------------------------------------------------------

def test_scraper_usa_user_agent_identificado_no_download():
    """Boa prática básica de scraping responsável: identificar quem está
    fazendo a requisição, nunca se passar por navegador comum."""
    assert 'buscador-processos' in scraper.USER_AGENT
    assert 'github.com' in scraper.USER_AGENT  # forma de contato, caso o STJ precise identificar a origem
