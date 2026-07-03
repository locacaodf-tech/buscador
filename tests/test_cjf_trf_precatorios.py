import asyncio

import pytest

from app.connectors.cjf_trf_precatorios import CjfTrfPrecatoriosConnector, FEDERAL_SOURCES
from app.connectors.base import SearchNotSupported


def test_capabilities_declaradas_conforme_pedido():
    types = {cap.search_type for cap in CjfTrfPrecatoriosConnector.capabilities}
    assert types == {
        'cnj', 'numero_processo', 'cpf', 'cnpj', 'oab', 'name',
        'requisitorio_number', 'precatorio_number', 'rpv_number',
    }


def test_todas_as_fontes_federais_mapeadas():
    assert set(FEDERAL_SOURCES) == {'CJF', 'TRF1', 'TRF2', 'TRF3', 'TRF4', 'TRF5', 'TRF6'}


def test_apenas_trf1_esta_marcado_como_implementado():
    for sigla, source in FEDERAL_SOURCES.items():
        if sigla == 'TRF1':
            assert source['implemented'] is True
        else:
            assert source['implemented'] is False


def test_cjf_nao_exige_credencial_mas_nao_tem_busca_propria():
    cjf = FEDERAL_SOURCES['CJF']
    assert cjf['requires_credentials'] is False
    assert cjf['source_type'] == 'dashboard_informativo'


def test_trf2_marcado_como_requer_credencial():
    trf2 = FEDERAL_SOURCES['TRF2']
    assert trf2['requires_credentials'] is True


def test_default_tribunal_e_trf1_quando_lista_vazia():
    connector = CjfTrfPrecatoriosConnector()
    assert connector._target_tribunal(None) == 'TRF1'
    assert connector._target_tribunal([]) == 'TRF1'


def test_target_tribunal_reconhece_sigla_valida_na_lista():
    connector = CjfTrfPrecatoriosConnector()
    assert connector._target_tribunal(['TRF3']) == 'TRF3'
    assert connector._target_tribunal(['trf5']) == 'TRF5'


def test_busca_em_trf2_retorna_item_de_erro_requer_credencial():
    connector = CjfTrfPrecatoriosConnector()
    result = asyncio.run(connector.search('cnj', '00008323520184013202', tribunals=['TRF2']))
    assert len(result) == 1
    assert 'requer credencial' in result[0]['error']
    assert result[0]['tribunal'] == 'TRF2'


def test_busca_em_trf3_retorna_item_de_erro_mapeada_nao_implementada():
    connector = CjfTrfPrecatoriosConnector()
    result = asyncio.run(connector.search('cnj', '00008323520184013202', tribunals=['TRF3']))
    assert len(result) == 1
    assert 'aguardando implementação' in result[0]['error']


def test_trf1_rejeita_tipo_de_busca_nao_suportado_ainda():
    connector = CjfTrfPrecatoriosConnector()
    with pytest.raises(SearchNotSupported):
        asyncio.run(connector.search('cpf', '12345678900', tribunals=['TRF1']))


def test_trf1_rejeita_numero_vazio():
    connector = CjfTrfPrecatoriosConnector()
    with pytest.raises(SearchNotSupported):
        asyncio.run(connector.search('cnj', '', tribunals=['TRF1']))


def test_trf1_url_de_consulta_usa_padrao_verificado(monkeypatch):
    connector = CjfTrfPrecatoriosConnector()
    captured = {}

    async def _fake_fetch(self, url):
        captured['url'] = url
        return '<html>nenhum registro encontrado</html>'

    monkeypatch.setattr(CjfTrfPrecatoriosConnector, '_fetch', _fake_fetch)
    result = asyncio.run(connector.search('cnj', '0032681-47.2017.4.01.3400', tribunals=['TRF1']))
    assert result == []  # "nenhum registro encontrado" -> lista vazia, não erro
    assert captured['url'] == (
        'https://processual.trf1.jus.br/consultaProcessual/processo.php'
        '?proc=00326814720174013400&secao=TRF1&pg=1&enviar=Pesquisar'
    )


def test_trf1_retorna_resultado_quando_encontra_processo(monkeypatch):
    connector = CjfTrfPrecatoriosConnector()

    async def _fake_fetch(self, url):
        return '<html><body>Processo 0032681-47.2017.4.01.3400 - Classe: Precatório</body></html>'

    monkeypatch.setattr(CjfTrfPrecatoriosConnector, '_fetch', _fake_fetch)
    result = asyncio.run(connector.search('cnj', '0032681-47.2017.4.01.3400', tribunals=['TRF1']))
    assert len(result) == 1
    assert result[0]['tribunal'] == 'TRF1'
    assert result[0]['source']['numeroProcesso'] == '0032681-47.2017.4.01.3400'
    assert 'Precatório' in result[0]['source']['texto_bruto']


def test_trf1_falha_de_rede_vira_item_de_erro_nao_excecao(monkeypatch):
    connector = CjfTrfPrecatoriosConnector()

    async def _boom(self, url):
        raise ConnectionError('timeout simulado')

    monkeypatch.setattr(CjfTrfPrecatoriosConnector, '_fetch', _boom)
    result = asyncio.run(connector.search('cnj', '0032681-47.2017.4.01.3400', tribunals=['TRF1']))
    assert len(result) == 1
    assert 'error' in result[0]
    assert 'Falha ao consultar TRF1' in result[0]['error']


def test_trf1_nunca_inventa_campos_oficiais_que_nao_extraiu(monkeypatch):
    """Regressão do incidente de 01/07: um artifact de demonstração mostrou
    número de requisitório/precatório/valor/fila fictícios como se fossem
    dado real. O backend nunca teve esse problema (esses campos nunca
    existiram na resposta real do conector), mas este teste trava
    explicitamente para que isso nunca vire verdade por acidente:
    o conector real só pode devolver numeroProcesso/fonte_url/texto_bruto/
    tribunal — nunca um valor monetário, requisitório, precatório, status
    de orçamento ou nome de credor que ele não extraiu de verdade.
    """
    import asyncio
    connector = CjfTrfPrecatoriosConnector.__new__(CjfTrfPrecatoriosConnector)

    async def _fake_fetch(self, url):
        return '<html><body>Processo 0032681-47.2017.4.01.3400 - Classe: Precatório</body></html>'

    monkeypatch.setattr(CjfTrfPrecatoriosConnector, '_fetch', _fake_fetch)
    result = asyncio.run(connector.search('cnj', '0032681-47.2017.4.01.3400', tribunals=['TRF1']))

    assert len(result) == 1
    source = result[0]['source']
    campos_proibidos = {
        'numero_requisitorio', 'numero_precatorio', 'valor_requisitado',
        'posicao_fila', 'status_requisitorio', 'ano_orcamento',
        'credor_nome', 'credor_documento', 'ente_devedor', 'natureza',
        'tipo_requisicao', 'data_expedicao', 'data_envio_tribunal',
    }
    campos_presentes = campos_proibidos & set(source.keys())
    assert not campos_presentes, (
        f'O conector real inventou campo(s) oficial(is) que não extraiu: {campos_presentes}. '
        'Esses campos só podem aparecer quando um parser real de fonte oficial os extrair de verdade.'
    )
    # Só o que o conector genuinamente confirma:
    assert set(source.keys()) <= {'tribunal', 'numeroProcesso', 'fonte_url', 'texto_bruto'}
