"""Testes do roteador central de buscas (_providers_to_try). Esse método
decide, pra cada combinação de provider solicitado + tipo de identificador,
quais conectores são tentados e em que ordem — é o "cérebro" de roteamento
do sistema inteiro, e nunca teve nenhum teste dedicado antes desta auditoria."""
from app.services.orchestrator import ProcessLookupOrchestrator, CONNECTOR_CLASSES, provider_capabilities


def _orchestrator():
    # _providers_to_try não usa self.db, então None é seguro só pra esses testes.
    return ProcessLookupOrchestrator(db=None)


def test_provider_explicito_ignora_o_tipo_de_busca():
    orch = _orchestrator()
    assert orch._providers_to_try('cjf_trf_precatorios', 'cpf') == ['cjf_trf_precatorios']
    assert orch._providers_to_try('datajud', 'unknown') == ['datajud']


def test_auto_com_cpf_cnpj_name_oab_tenta_tribunal_precatorios():
    orch = _orchestrator()
    for tipo in ['cpf', 'cnpj', 'name', 'oab']:
        assert orch._providers_to_try('auto', tipo) == ['tribunal_precatorios']


def test_multi_com_cpf_inclui_cjf_trf1_e_datajud_tambem():
    orch = _orchestrator()
    resultado = orch._providers_to_try('multi', 'cpf')
    assert resultado == ['tribunal_precatorios', 'cjf_trf_precatorios', 'datajud']


def test_auto_com_cnj_so_tenta_datajud():
    orch = _orchestrator()
    assert orch._providers_to_try('auto', 'cnj') == ['datajud']
    assert orch._providers_to_try('auto', 'numero_processo') == ['datajud']


def test_multi_com_cnj_inclui_cjf_trf1():
    orch = _orchestrator()
    resultado = orch._providers_to_try('multi', 'cnj')
    assert resultado == ['datajud', 'cjf_trf_precatorios']


def test_auto_com_sequencial_precatorio_nao_inclui_stj():
    """Achado documentado no código: sequencial isolado no modo auto não deve
    ir pro STJ, porque sem saber o órgão emissor geraria falso match."""
    orch = _orchestrator()
    resultado = orch._providers_to_try('auto', 'precatorio_number')
    assert 'stj_precatorios' not in resultado
    assert resultado == ['tribunal_precatorios']


def test_multi_com_sequencial_precatorio_inclui_stj():
    orch = _orchestrator()
    resultado = orch._providers_to_try('multi', 'requisitorio_number')
    assert 'stj_precatorios' in resultado


def test_entidade_devedora_so_vai_pro_mpo_siop():
    orch = _orchestrator()
    assert orch._providers_to_try('auto', 'entidade_devedora') == ['mpo_siop_precatorios']
    assert orch._providers_to_try('multi', 'entidade_devedora') == ['mpo_siop_precatorios']


def test_tipo_desconhecido_cai_no_fallback_generico():
    orch = _orchestrator()
    resultado = orch._providers_to_try('auto', 'algum_tipo_que_nao_existe')
    assert resultado == ['datajud', 'tribunal_precatorios']


def test_connector_invalido_levanta_erro_claro():
    orch = _orchestrator()
    try:
        orch._connector('provedor_que_nao_existe')
        assert False, 'deveria ter levantado ValueError'
    except ValueError as e:
        assert 'inválido' in str(e)


def test_todos_os_providers_do_roteador_existem_no_registro_de_conectores():
    """Garante que _providers_to_try nunca aponta pra um nome de conector que
    não está registrado em CONNECTOR_CLASSES — evitaria um erro só em runtime."""
    orch = _orchestrator()
    combinacoes = [
        ('auto', 'cpf'), ('multi', 'cpf'), ('auto', 'cnj'), ('multi', 'cnj'),
        ('auto', 'precatorio_number'), ('multi', 'precatorio_number'),
        ('auto', 'entidade_devedora'), ('auto', 'desconhecido'),
    ]
    for requested, tipo in combinacoes:
        for provider in orch._providers_to_try(requested, tipo):
            assert provider in CONNECTOR_CLASSES, f'{provider} nao esta registrado em CONNECTOR_CLASSES'


def test_provider_capabilities_devolve_todos_os_conectores_registrados():
    caps = provider_capabilities()
    assert set(caps.keys()) == set(CONNECTOR_CLASSES.keys())
    for name, info in caps.items():
        assert 'supported_search_types' in info
