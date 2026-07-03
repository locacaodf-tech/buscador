import asyncio

import pytest

from app.connectors.base import SearchNotSupported
from app.connectors.mpo_siop_precatorios import (
    MpoSiopPrecatoriosConnector,
    esfera_da_justica,
    normalize_mpo_row,
    orcamento_summary,
    parse_mpo_csv_text,
    _parse_valor_br,
)

# CSV sintético usando os nomes de coluna EXATOS da Nota Metodológica oficial
# do SOF/MPO (separador ';', decimal com vírgula — formato confirmado ao vivo
# em arquivo do mesmo domínio).
CSV_SINTETICO = (
    'Chave;Exercício;Código do Tribunal;Nome do Tribunal;Tribunal Expedidor;'
    'Data de Ajuizamento da Ação Originária;Data da Autuação;Tipo de Despesa;'
    'Código da UO Executada;Nome da UO Executada;Natureza da Despesa;Tipo de Causa;'
    'Valor Original do Precatório;Valor Atualizado\n'
    'ABC123;2026;12000;Justiça Federal;TRF 1ª Região;2017-05-10;2024-04-01;12;'
    '25201;Instituto Nacional do Seguro Social - INSS;3;Previdenciária;'
    '150.000,50;187.320,10\n'
    'DEF456;2026;12000;Justiça Federal;TRF 1ª Região;2015-02-20;2024-03-15;21;'
    '26298;Universidade Federal de Minas Gerais;4;Administrativa;'
    '80.500,00;95.010,99\n'
)


def test_parse_valor_br():
    assert _parse_valor_br('150.000,50') == pytest.approx(150000.50)
    assert _parse_valor_br('') is None
    assert _parse_valor_br(None) is None
    assert _parse_valor_br('abc') is None


def test_esfera_da_justica():
    assert esfera_da_justica('12000') == 'Justiça Federal'
    assert esfera_da_justica('11000') == 'STJ'
    assert esfera_da_justica('15102') == 'Justiça do Trabalho'
    assert esfera_da_justica(None) is None
    assert esfera_da_justica('99999') is None  # prefixo desconhecido -> None, não palpite


def test_parse_csv_com_colunas_oficiais():
    records = parse_mpo_csv_text(CSV_SINTETICO, 2026)
    assert len(records) == 2
    rec = records[0]
    assert rec['chave'] == 'ABC123'
    assert rec['exercicio'] == 2026
    assert rec['entidade_devedora'] == 'Instituto Nacional do Seguro Social - INSS'
    assert rec['valor_original'] == pytest.approx(150000.50)
    assert rec['valor_atualizado'] == pytest.approx(187320.10)
    assert rec['tipo_despesa_codigo'] == '12'
    assert 'previdenciários' in rec['tipo_despesa_label']
    assert rec['esfera_justica'] == 'Justiça Federal'
    assert rec['fonte_url'].endswith('expedidos_2026.csv')


def test_normalize_row_campo_ausente_vira_none():
    rec = normalize_mpo_row({'Exercício': '2026'}, 2026)
    assert rec['entidade_devedora'] is None
    assert rec['valor_original'] is None
    assert rec['tipo_despesa_label'] is None


def _connector_com_dados(monkeypatch):
    connector = MpoSiopPrecatoriosConnector()
    records = parse_mpo_csv_text(CSV_SINTETICO, 2026)

    async def _fake(self, ano):
        return records

    monkeypatch.setattr(MpoSiopPrecatoriosConnector, '_records_for_year', _fake)
    return connector


def test_busca_por_entidade_devedora(monkeypatch):
    connector = _connector_com_dados(monkeypatch)
    result = asyncio.run(connector.search('entidade_devedora', 'INSS', extra_params={'ano_orcamento': 2026}))
    assert len(result) == 1
    assert result[0]['source']['entidade_devedora'] == 'Instituto Nacional do Seguro Social - INSS'
    assert result[0]['source']['valor_atualizado'] == pytest.approx(187320.10)


def test_busca_case_insensitive_e_parcial(monkeypatch):
    connector = _connector_com_dados(monkeypatch)
    result = asyncio.run(connector.search('entidade_devedora', 'universidade federal', extra_params={'ano_orcamento': 2026}))
    assert len(result) == 1
    assert 'Minas Gerais' in result[0]['source']['entidade_devedora']


def test_filtro_tipo_despesa(monkeypatch):
    connector = _connector_com_dados(monkeypatch)
    so_21 = asyncio.run(connector.search('entidade_devedora', 'e', extra_params={'ano_orcamento': 2026, 'tipo_despesa': 21}))
    assert len(so_21) == 1
    assert so_21[0]['source']['tipo_despesa_codigo'] == '21'


def test_ano_obrigatorio():
    connector = MpoSiopPrecatoriosConnector()
    with pytest.raises(SearchNotSupported, match='ano_orcamento'):
        asyncio.run(connector.search('entidade_devedora', 'INSS'))


def test_tipo_nao_suportado_explica_limitacao_legal():
    connector = MpoSiopPrecatoriosConnector()
    with pytest.raises(SearchNotSupported, match='LDO'):
        asyncio.run(connector.search('cpf', '12345678900'))


def test_ano_fora_do_intervalo_vira_erro_amigavel(monkeypatch):
    connector = MpoSiopPrecatoriosConnector()
    result = asyncio.run(connector.search('entidade_devedora', 'INSS', extra_params={'ano_orcamento': 1999}))
    assert len(result) == 1
    assert 'error' in result[0]


def test_orcamento_summary():
    records = parse_mpo_csv_text(CSV_SINTETICO, 2026)
    summary = orcamento_summary(records)
    assert summary['total_registros'] == 2
    assert summary['soma_valor_original'] == pytest.approx(230500.50)
    assert summary['soma_valor_atualizado'] == pytest.approx(282331.09)
