import asyncio
import io

import pytest

from app.connectors.base import SearchNotSupported
from app.connectors.stj_precatorios import (
    StjPrecatoriosConnector,
    discover_file_links,
    find_header_row,
    infer_file_metadata,
    match_records,
    parse_stj_sheet,
    parse_workbook_bytes,
    _parse_valor,
)


# ---------------------------------------------------------------------------
# Planilha sintética reproduzindo EXATAMENTE a estrutura do print real do STJ
# (28/06/2026): ordem | classe | sequencial | processo | prioridade | valor |
# previsão. Inclusive a linha real do print: 143 | PRC | 15547 |
# 0506671-51.2025.3.00.0000 | Idoso | 1.708.161,78 | fevereiro/2026.
# ---------------------------------------------------------------------------

def build_synthetic_xlsx() -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'PRCs'
    ws.append(['Relação de Precatórios Expedidos - STJ'])  # linha de título, antes do cabeçalho
    ws.append([])
    ws.append(['Ordem', 'Classe', 'Sequencial', 'Processo', 'Prioridade', 'Valor', 'Previsão de pagamento'])
    ws.append([142, 'PRC', 15546, '0506670-66.2025.3.00.0000', None, '954.220,10', 'fevereiro/2026'])
    ws.append([143, 'PRC', 15547, '0506671-51.2025.3.00.0000', 'Idoso', '1.708.161,78', 'fevereiro/2026'])
    ws.append([144, 'PRC', 15548, '0506675-88.2025.3.00.0000', 'Idoso', '1.154.779,51', 'fevereiro/2026'])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


FILE_META = {'categoria': 'expedidos', 'natureza': 'alimentar', 'ano_expedicao': 2025, 'ano_orcamento': 2026, 'tipo_requisicao': 'precatorio'}
FONTE = 'https://www.stj.jus.br/exemplo/Precatorios-Expedidos-Alimentar.xlsm'


def _connector_with_synthetic_data(monkeypatch) -> StjPrecatoriosConnector:
    connector = StjPrecatoriosConnector()
    records = parse_workbook_bytes(build_synthetic_xlsx(), FILE_META, FONTE)

    async def _fake_page(self):
        return '<a href="/exemplo/Precatorios-Expedidos-Alimentar.xlsm">2025 - inclusos na proposta orçamentária de 2026 (Alimentar)</a>'

    async def _fake_download(self, link):
        return records

    monkeypatch.setattr(StjPrecatoriosConnector, '_fetch_page', _fake_page)
    monkeypatch.setattr(StjPrecatoriosConnector, '_download_records', _fake_download)
    return connector


# ------------------------- Funções puras -------------------------

def test_parse_valor_formato_brasileiro():
    assert _parse_valor('1.708.161,78') == pytest.approx(1708161.78)
    assert _parse_valor('R$ 954.220,10') == pytest.approx(954220.10)
    assert _parse_valor(1708161.78) == pytest.approx(1708161.78)
    assert _parse_valor('') is None
    assert _parse_valor(None) is None
    assert _parse_valor('n/d') is None  # texto não numérico -> None, nunca palpite


def test_infer_file_metadata_proposta():
    meta = infer_file_metadata('https://stj.jus.br/PRCs-proposta-2027.xlsx')
    assert meta['categoria'] == 'proposta'
    assert meta['ano_orcamento'] == 2027


def test_infer_file_metadata_expedidos_com_dois_anos():
    meta = infer_file_metadata(
        'https://stj.jus.br/Precatorios-2026--Expedidos-Alimentar-2027.xlsm',
        link_context='2026 - inclusos na proposta orçamentária de 2027',
    )
    assert meta['categoria'] == 'expedidos'
    assert meta['natureza'] == 'alimentar'
    assert meta['ano_expedicao'] == 2026
    assert meta['ano_orcamento'] == 2027


def test_discover_file_links_encontra_xlsx_e_xlsm():
    html = (
        '<a href="https://www.stj.jus.br/a/PRCs-proposta-2027.xlsx">PRCs Proposta - 2027</a>'
        '<a href="/b/Precatorios-Expedidos-Comum.xlsm">Comum</a>'
    )
    links = discover_file_links(html)
    assert len(links) == 2
    assert links[0]['url'].endswith('PRCs-proposta-2027.xlsx')
    assert links[1]['url'].startswith('https://www.stj.jus.br/')  # relativo vira absoluto


def test_find_header_row_ignora_titulo_antes_do_cabecalho():
    rows = [
        ('Relação de Precatórios',),
        (),
        ('Ordem', 'Classe', 'Sequencial', 'Processo', 'Prioridade', 'Valor', 'Previsão de pagamento'),
        (143, 'PRC', 15547, '0506671-51.2025.3.00.0000', 'Idoso', '1.708.161,78', 'fevereiro/2026'),
    ]
    header = find_header_row(rows)
    assert header is not None
    idx, mapping = header
    assert idx == 2
    assert mapping['sequencial'] == 2
    assert mapping['numero_processo'] == 3
    assert mapping['valor'] == 5


def test_parse_stj_sheet_reproduz_linha_do_print_real():
    rows = [
        ('Ordem', 'Classe', 'Sequencial', 'Processo', 'Prioridade', 'Valor', 'Previsão de pagamento'),
        (143, 'PRC', 15547, '0506671-51.2025.3.00.0000', 'Idoso', '1.708.161,78', 'fevereiro/2026'),
    ]
    records = parse_stj_sheet(rows, FILE_META, FONTE)
    assert len(records) == 1
    rec = records[0]
    assert rec['sequencial'] == '15547'
    assert rec['classe'] == 'PRC'
    assert rec['numero_processo'] == '0506671-51.2025.3.00.0000'
    assert rec['valor'] == pytest.approx(1708161.78)
    assert rec['previsao_pagamento'] == 'fevereiro/2026'
    assert rec['prioridade'] == 'Idoso'
    assert rec['ano_orcamento'] == 2026
    assert rec['fonte_url'] == FONTE
    assert rec['linha_arquivo'] == 2


def test_parse_stj_sheet_campo_ausente_vira_none_nunca_inventado():
    rows = [
        ('Sequencial', 'Processo'),  # planilha mínima, sem valor/credor/etc
        (15547, '0506671-51.2025.3.00.0000'),
    ]
    records = parse_stj_sheet(rows, {'categoria': 'expedidos'}, FONTE)
    assert len(records) == 1
    rec = records[0]
    assert rec['valor'] is None
    assert rec['credor_nome'] is None
    assert rec['previsao_pagamento'] is None
    assert rec['entidade_devedora'] is None


# ------------------------- Conector end-to-end (com dados sintéticos) -------------------------

def test_busca_por_sequencial_retorna_valor_correto_do_print(monkeypatch):
    connector = _connector_with_synthetic_data(monkeypatch)
    result = asyncio.run(connector.search('precatorio_number', '15547'))
    assert len(result) == 1
    source = result[0]['source']
    assert source['sequencial'] == '15547'
    # O valor que o painel mostrar TEM que ser este (o do arquivo oficial),
    # nunca os R$ 187.452,36 fictícios do incidente de demonstração.
    assert source['valor'] == pytest.approx(1708161.78)
    assert source['fonte_url'] == FONTE


def test_busca_por_processo_cnj(monkeypatch):
    connector = _connector_with_synthetic_data(monkeypatch)
    result = asyncio.run(connector.search('cnj', '0506671-51.2025.3.00.0000'))
    assert len(result) == 1
    assert result[0]['source']['sequencial'] == '15547'


def test_busca_sequencial_inexistente_retorna_vazio_nao_inventa(monkeypatch):
    connector = _connector_with_synthetic_data(monkeypatch)
    result = asyncio.run(connector.search('precatorio_number', '99999'))
    assert result == []


def test_filtro_ano_orcamento_opcional(monkeypatch):
    connector = _connector_with_synthetic_data(monkeypatch)
    ok = asyncio.run(connector.search('precatorio_number', '15547', extra_params={'ano_orcamento': 2026}))
    assert len(ok) == 1
    outro_ano = asyncio.run(connector.search('precatorio_number', '15547', extra_params={'ano_orcamento': 2030}))
    assert outro_ano == []


def test_tipo_nao_suportado_gera_erro_claro():
    connector = StjPrecatoriosConnector()
    with pytest.raises(SearchNotSupported, match='CPF/nome'):
        asyncio.run(connector.search('cpf', '12345678900'))


def test_falha_de_rede_vira_item_de_erro(monkeypatch):
    connector = StjPrecatoriosConnector()

    async def _boom(self):
        raise ConnectionError('rede indisponível')

    monkeypatch.setattr(StjPrecatoriosConnector, '_fetch_page', _boom)
    result = asyncio.run(connector.search('precatorio_number', '15547'))
    assert len(result) == 1
    assert 'error' in result[0]


def test_valores_ficticios_do_incidente_nunca_aparecem_em_resultado_real(monkeypatch):
    """Regressão direta do incidente de 01/07: os valores fictícios que
    apareceram na tela (OF-2027/004521, PRC-2027/0089341, 187452.36, fila 1542)
    não podem existir em nenhuma resposta do conector real."""
    connector = _connector_with_synthetic_data(monkeypatch)
    result = asyncio.run(connector.search('precatorio_number', '15547'))
    dump = str(result)
    for proibido in ['OF-2027/004521', 'PRC-2027/0089341', '187452.36', '187.452', "'posicao_fila': 1542"]:
        assert proibido not in dump, f'valor fictício do incidente vazou para resultado real: {proibido}'


# ---------------------------------------------------------------------------
# Busca por nome do credor — feature real, sem depender de provedor comercial
# pago: se a planilha do STJ tiver coluna de credor/beneficiário, dá pra
# achar o precatório pelo nome, gratuitamente, nos dados que o próprio
# usuário já carregou.
# ---------------------------------------------------------------------------

def _registros_com_credor():
    return [
        {'sequencial': '15547', 'numero_processo': '05066715120253000000', 'credor_nome': 'MARIA DA SILVA SOUZA', 'valor': 1708161.78},
        {'sequencial': '15548', 'numero_processo': '05066725120253000000', 'credor_nome': 'JOÃO PEREIRA SANTOS', 'valor': 95000.0},
    ]


def test_busca_por_nome_encontra_parcial_minusculo_sem_acento():
    registros = _registros_com_credor()
    resultado = match_records(registros, 'name', 'maria da silva')
    assert len(resultado) == 1
    assert resultado[0]['sequencial'] == '15547'


def test_busca_por_nome_e_case_e_accent_insensitive():
    registros = _registros_com_credor()
    resultado = match_records(registros, 'name', 'JOÃO PEREIRA')
    assert len(resultado) == 1
    assert resultado[0]['sequencial'] == '15548'

    resultado2 = match_records(registros, 'name', 'joao pereira')  # sem acento, minusculo
    assert len(resultado2) == 1
    assert resultado2[0]['sequencial'] == '15548'


def test_busca_por_nome_sem_correspondencia_devolve_vazio():
    registros = _registros_com_credor()
    resultado = match_records(registros, 'name', 'FULANO INEXISTENTE')
    assert resultado == []


def test_busca_por_nome_ignora_registro_sem_coluna_credor():
    registros = [{'sequencial': '999', 'numero_processo': '123', 'credor_nome': None}]
    resultado = match_records(registros, 'name', 'qualquer nome')
    assert resultado == []


def test_credor_nome_e_detectado_de_planilha_real_com_essa_coluna():
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

    meta = infer_file_metadata('teste.xlsx')
    records = parse_workbook_bytes(buf.getvalue(), meta, 'upload:teste.xlsx')
    assert len(records) == 1
    assert records[0]['credor_nome'] == 'MARIA DA SILVA SOUZA'
