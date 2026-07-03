import pytest

from app.config import get_settings
from app.connectors.base import ProviderNotConfigured
from app.connectors.judit import JuditConnector


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    # Settings usa lru_cache; sem isso, monkeypatch de env var em um teste
    # vazaria para os demais.
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_capabilities_match_exact_spec():
    types = {cap.search_type for cap in JuditConnector.capabilities}
    assert types == {'cpf', 'cnpj', 'oab', 'cnj', 'name'}


def test_raises_when_disabled_or_missing_key(monkeypatch):
    monkeypatch.delenv('JUDIT_ENABLED', raising=False)
    monkeypatch.delenv('JUDIT_API_KEY', raising=False)
    with pytest.raises(ProviderNotConfigured):
        JuditConnector()


def test_raises_when_enabled_but_key_empty(monkeypatch):
    monkeypatch.setenv('JUDIT_ENABLED', 'true')
    monkeypatch.setenv('JUDIT_API_KEY', '')
    with pytest.raises(ProviderNotConfigured):
        JuditConnector()


def test_headers_use_api_key_never_bearer(monkeypatch):
    monkeypatch.setenv('JUDIT_ENABLED', 'true')
    monkeypatch.setenv('JUDIT_API_KEY', 'chave-de-teste')
    connector = JuditConnector()
    headers = connector._headers()
    assert headers['api-key'] == 'chave-de-teste'
    assert 'Authorization' not in headers
    assert 'Bearer' not in str(headers)


def test_external_search_type_cpf_cnpj_oab_cnj_sao_fixos(monkeypatch):
    # JUDIT_NAME_SEARCH_TYPE não deve afetar nenhum tipo além de 'name'.
    monkeypatch.setenv('JUDIT_NAME_SEARCH_TYPE', 'nome')
    assert JuditConnector.external_search_type('cpf') == 'cpf'
    assert JuditConnector.external_search_type('cnpj') == 'cnpj'
    assert JuditConnector.external_search_type('oab') == 'oab'
    assert JuditConnector.external_search_type('cnj') == 'cnj'


def test_external_search_type_name_usa_default_name(monkeypatch):
    monkeypatch.delenv('JUDIT_NAME_SEARCH_TYPE', raising=False)
    assert JuditConnector.external_search_type('name') == 'name'


def test_external_search_type_name_respeita_env_var(monkeypatch):
    monkeypatch.setenv('JUDIT_NAME_SEARCH_TYPE', 'nome')
    assert JuditConnector.external_search_type('name') == 'nome'


def test_build_search_payload_name_usa_default_name(monkeypatch):
    monkeypatch.delenv('JUDIT_NAME_SEARCH_TYPE', raising=False)
    payload = JuditConnector.build_search_payload('name', 'Fulano de Tal')
    assert payload['search']['search_type'] == 'name'


def test_build_search_payload_name_respeita_judit_name_search_type_nome(monkeypatch):
    monkeypatch.setenv('JUDIT_NAME_SEARCH_TYPE', 'nome')
    payload = JuditConnector.build_search_payload('name', 'Fulano de Tal')
    assert payload['search']['search_type'] == 'nome'
    # search_key e demais campos continuam intactos, só o search_type muda.
    assert payload['search']['search_key'] == 'Fulano de Tal'


def test_build_search_payload_outros_tipos_ignoram_judit_name_search_type(monkeypatch):
    monkeypatch.setenv('JUDIT_NAME_SEARCH_TYPE', 'nome')
    for internal_type in ('cpf', 'cnpj', 'oab', 'cnj'):
        payload = JuditConnector.build_search_payload(internal_type, 'valor-teste')
        assert payload['search']['search_type'] == internal_type


def test_build_search_payload_minimo():
    payload = JuditConnector.build_search_payload('cpf', '12345678900')
    assert payload == {'search': {'search_type': 'cpf', 'search_key': '12345678900'}}


def test_build_search_payload_cache_e_tribunais():
    options = {'use_cache_days': 7, 'tribunals': ['TRF1', 'TRF2']}
    payload = JuditConnector.build_search_payload('cnj', '00008323520184013202', options)
    assert payload['cache_ttl_in_days'] == 7
    assert payload['search']['search_params']['filter']['tribunals'] == {
        'keys': ['TRF1', 'TRF2'],
        'not_equal': False,
    }


def test_build_search_payload_filtros_side_amount_distribution_date():
    options = {
        'extra_params': {
            'side': 'passive',
            'amount_gte': 1000,
            'distribution_date_gte': '2020-01-01',
            'nome_mae': 'Maria',
        }
    }
    payload = JuditConnector.build_search_payload('name', 'Fulano de Tal', options)
    filt = payload['search']['search_params']['filter']
    assert filt['side'] == 'passive'
    assert filt['amount_gte'] == 1000
    assert filt['distribution_date_gte'] == '2020-01-01'
    # Campos livres que não são filtro estruturado continuam indo direto em search_params.
    assert payload['search']['search_params']['nome_mae'] == 'Maria'


def test_build_search_payload_sem_opcoes_extras_nao_gera_search_params_vazio():
    payload = JuditConnector.build_search_payload('oab', 'SP12345', {'tribunals': [], 'extra_params': {}})
    assert 'search_params' not in payload['search']


def test_search_rejeita_tipo_nao_suportado():
    connector = object.__new__(JuditConnector)  # evita exigir configuração para este teste
    with pytest.raises(Exception) as exc_info:
        import asyncio
        asyncio.run(connector.search('precatorio_number', 'PRC-2027-000000'))
    assert 'precatorio_number' in str(exc_info.value)


def test_search_erro_de_rede_vira_item_de_erro_em_vez_de_excecao(monkeypatch):
    import asyncio
    from app.connectors.base import ConnectorError

    monkeypatch.setenv('JUDIT_ENABLED', 'true')
    monkeypatch.setenv('JUDIT_API_KEY', 'chave-de-teste')
    connector = JuditConnector()

    async def _boom(*args, **kwargs):
        raise ConnectorError('Judit HTTP 403: bloqueado')

    monkeypatch.setattr(connector, 'create_request', _boom)

    result = asyncio.run(connector.search('cpf', '12345678900'))
    assert result == [{'provider': 'judit', 'tribunal': None, 'error': 'Judit HTTP 403: bloqueado'}]
