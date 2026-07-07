"""Testes do conector DataJud — inclui a correção da auditoria externa: o
número CNJ já indica o tribunal (dígitos J.TR), então uma busca por CNJ sem
tribunal explícito deve consultar SÓ o tribunal certo, não os 6 TRFs à toa."""
import asyncio

import pytest

from app.connectors.base import ConnectorError, SearchNotSupported
from app.connectors.datajud import DataJudConnector


def test_inicializa_com_a_chave_publica_padrao():
    connector = DataJudConnector()
    assert connector.api_key
    assert connector.headers['Authorization'].startswith('APIKey ')


def test_endpoint_for_tribunal_conhecido():
    connector = DataJudConnector()
    assert connector.endpoint_for('TRF1') == 'https://api-publica.datajud.cnj.jus.br/api_publica_trf1/_search'


def test_endpoint_for_tribunal_desconhecido_levanta_erro_claro():
    connector = DataJudConnector()
    with pytest.raises(ConnectorError, match='não suportado'):
        connector.endpoint_for('TRIBUNAL_INVENTADO')


def test_search_cpf_cnpj_name_oab_nao_e_suportado():
    connector = DataJudConnector()
    for tipo in ['cpf', 'cnpj', 'name', 'oab']:
        with pytest.raises(SearchNotSupported):
            asyncio.run(connector.search(tipo, 'qualquer valor'))


def test_search_by_cnj_exige_20_digitos():
    connector = DataJudConnector()
    with pytest.raises(SearchNotSupported, match='20 dígitos'):
        asyncio.run(connector.search_by_cnj('123'))


def test_search_sem_tribunal_explicito_infere_pelo_proprio_cnj(monkeypatch):
    """Achado real da auditoria externa: sem isso, toda busca por CNJ
    consultava os 6 TRFs de uma vez, mesmo quando o número já dizia qual
    era o certo (segmento 4 = federal, TR = 01 a 06 = TRF1 a TRF6)."""
    connector = DataJudConnector()
    chamadas = []

    async def fake_search_by_cnj(cnj, tribunals=None, max_results=50):
        chamadas.append(tribunals)
        return []

    monkeypatch.setattr(connector, 'search_by_cnj', fake_search_by_cnj)
    asyncio.run(connector.search('cnj', '0032681-47.2017.4.01.3400'))
    assert chamadas[-1] == ['TRF1'], f'deveria ter consultado só TRF1, consultou {chamadas[-1]}'


def test_search_com_cnj_estadual_infere_o_tj_certo(monkeypatch):
    """Achado real da segunda rodada de auditoria: CNJ de segmento estadual
    (8) também tem o tribunal certo nos próprios dígitos — TR=07 é TJDFT,
    confirmado contra a tabela oficial do CNJ (Resolução 65/2008)."""
    connector = DataJudConnector()
    chamadas = []

    async def fake_search_by_cnj(cnj, tribunals=None, max_results=50):
        chamadas.append(tribunals)
        return []

    monkeypatch.setattr(connector, 'search_by_cnj', fake_search_by_cnj)
    asyncio.run(connector.search('cnj', '0000000-00.2020.8.07.0001'))  # segmento 8, TR=07 = TJDFT
    assert chamadas[-1] == ['TJDFT']


def test_search_com_cnj_de_segmento_nao_coberto_cai_no_fallback(monkeypatch):
    """Segmentos não cobertos pela inferência (ex.: 6 = Justiça Eleitoral)
    não permitem inferir um tribunal único — aí sim mantém o fallback
    antigo (consultar os 6 TRFs). Trabalhista (segmento 5) passou a ser
    coberto na v31 (TRT1-24) — ver test_datajud_trabalhista_agora_e_coberto
    logo abaixo, que substitui o comportamento antigo testado aqui."""
    connector = DataJudConnector()
    chamadas = []

    async def fake_search_by_cnj(cnj, tribunals=None, max_results=50):
        chamadas.append(tribunals)
        return []

    monkeypatch.setattr(connector, 'search_by_cnj', fake_search_by_cnj)
    asyncio.run(connector.search('cnj', '0000000-00.2020.6.02.0001'))  # segmento 6 = eleitoral, genuinamente não coberto
    assert len(chamadas[-1]) == 6


def test_datajud_trabalhista_agora_e_coberto(monkeypatch):
    """v31: Justiça do Trabalho (segmento 5) passou a ter tribunal inferido
    (TRT1-24), então o DataJud agora consulta só o TRT certo, não os 6 TRFs
    por fallback — mais preciso, achado necessário pro WhatsApp Intake
    (exemplo do Fortaleza/CE precisa inferir TRT7 corretamente)."""
    connector = DataJudConnector()
    chamadas = []

    async def fake_search_by_cnj(cnj, tribunals=None, max_results=50):
        chamadas.append(tribunals)
        return []

    monkeypatch.setattr(connector, 'search_by_cnj', fake_search_by_cnj)
    asyncio.run(connector.search('cnj', '0000765-97.2023.5.07.0016'))  # segmento 5, tribunal 07 = TRT7
    assert chamadas[-1] == ['TRT7']


def test_search_respeita_tribunal_explicito_mesmo_com_cnj_inferivel(monkeypatch):
    """Se o chamador já informou o tribunal explicitamente, isso tem
    prioridade sobre a inferência automática."""
    connector = DataJudConnector()
    chamadas = []

    async def fake_search_by_cnj(cnj, tribunals=None, max_results=50):
        chamadas.append(tribunals)
        return []

    monkeypatch.setattr(connector, 'search_by_cnj', fake_search_by_cnj)
    asyncio.run(connector.search('cnj', '0032681-47.2017.4.01.3400', tribunals=['TRF2']))
    assert chamadas[-1] == ['TRF2']
