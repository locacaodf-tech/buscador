import pytest

from app.services.portal_automation import (
    PORTAL_AUTOMATION_STUBS,
    AutomationStatus,
    StubPortalAutomationConnector,
)


def test_todos_os_stubs_pedidos_existem():
    esperados = {
        'trf1_precatorios_browser', 'trf2_precatorios_browser', 'trf3_requisicoes_browser',
        'trf4_precatorios_browser', 'trf5_precatorios_browser', 'trf6_precatorios_browser',
        'tjdft_sapre_browser', 'tjsp_precatorios_browser',
    }
    assert esperados == set(PORTAL_AUTOMATION_STUBS)


def test_stub_can_search_e_sempre_false():
    for connector in PORTAL_AUTOMATION_STUBS.values():
        assert connector.can_search('cpf') is False


def test_stub_build_query_levanta_not_implemented():
    connector = PORTAL_AUTOMATION_STUBS['trf1_precatorios_browser']
    with pytest.raises(NotImplementedError):
        connector.build_query('cpf', '12345678900')


def test_stub_run_browser_search_levanta_not_implemented():
    import asyncio
    connector = PORTAL_AUTOMATION_STUBS['tjdft_sapre_browser']
    with pytest.raises(NotImplementedError):
        asyncio.run(connector.run_browser_search({}))


def test_not_implemented_result_tem_status_correto():
    connector = PORTAL_AUTOMATION_STUBS['trf5_precatorios_browser']
    result = connector.not_implemented_result()
    assert result.status == AutomationStatus.NOT_IMPLEMENTED
    assert result.source_id == 'trf5_precatorios_browser'
    assert result.fonte_url.startswith('https://')
    assert 'não implementada' in result.message


def test_stub_generico_customizado():
    c = StubPortalAutomationConnector('teste_x', 'https://exemplo.jus.br', notes='nota de teste')
    with pytest.raises(NotImplementedError, match='nota de teste'):
        c.extract_results(None)
