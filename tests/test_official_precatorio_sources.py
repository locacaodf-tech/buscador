from app.services.official_precatorio_sources import (
    official_precatorio_sources,
    official_precatorio_sources_summary,
    build_precatorio_route_plan,
    sources_for_search,
)


def test_registry_has_core_precatorio_sources():
    sources = official_precatorio_sources()
    for key in [
        'sispreq_pdpj',
        'mpo_siop_precatorios_dados_abertos',
        'cjf_precatorios',
        'trf1_precatorios',
        'trf3_requisicoes_pagamento',
        'trf5_precatorios',
        'trf6_precatorios',
        'tjdft_sapre',
    ]:
        assert key in sources


def test_plan_for_precatorio_number_requires_tribunal_and_budget_year_when_relevant():
    plan = build_precatorio_route_plan('precatorio_number', '12345', {})
    assert 'tribunal/trf' in plan['missing_recommended_fields']
    assert 'ano_orcamento (quando a pergunta for LOA/orçamento)' in plan['missing_recommended_fields']
    assert any(layer['layer'] == 'loa_orcamento' for layer in plan['route_layers'])


def test_sources_for_trf1_prioritizes_trf1_and_national_layers():
    sources = sources_for_search('cnj', {'tribunal': 'TRF1'})
    keys = [src.key for src in sources]
    assert 'trf1_precatorios' in keys
    assert 'sispreq_pdpj' in keys
    assert 'mpo_siop_precatorios_dados_abertos' in keys


def test_tjdft_source_returns_budget_and_queue_fields():
    sources = official_precatorio_sources()
    tjdft = sources['tjdft_sapre']
    assert 'ano_orcamento' in tjdft['fields_returned']
    assert 'situacao' in tjdft['fields_returned']
    assert 'ordem_classificacao' in tjdft['fields_returned']


def test_registry_cobre_todos_os_ramos_pedidos():
    sources = official_precatorio_sources()
    # Justiça Federal
    for key in ['cjf_precatorios', 'trf1_precatorios', 'trf2_precatorios', 'trf3_requisicoes_pagamento',
                'trf4_precatorios', 'trf5_precatorios', 'trf6_precatorios']:
        assert key in sources
    # Justiça estadual: amostra + TJDFT/TJSP que já existiam
    for key in ['tjac', 'tjba', 'tjmg', 'tjrj', 'tjrs', 'tjdft_sapre', 'tjsp_precatorios']:
        assert key in sources
    assert len([k for k, v in sources.items() if v['scope'] == 'estadual']) == 25
    # Justiça do Trabalho: 24 TRTs + CSJT
    for key in ['trt1', 'trt24', 'csjt_precatorios']:
        assert key in sources
    assert len([k for k, v in sources.items() if v['scope'] == 'trabalhista']) == 24
    # Tribunais superiores
    for key in ['stf_precatorios', 'stj_precatorios', 'tst_precatorios', 'stm_precatorios']:
        assert key in sources


def test_fontes_nao_pesquisadas_nao_inventam_capacidades():
    sources = official_precatorio_sources()
    nao_pesquisadas = [v for v in sources.values() if v['integration_status'] == 'not_researched']
    assert len(nao_pesquisadas) >= 49  # 25 TJs + 24 TRTs (menos os já pesquisados: TJDFT, TJSP) + CSJT
    for src in nao_pesquisadas:
        assert src['supports_search_types'] == []
        assert src['fields_returned'] == []
        assert src['official_url'].startswith('https://')


def test_trf1_marcado_como_parcialmente_implementado():
    sources = official_precatorio_sources()
    assert sources['trf1_precatorios']['integration_status'] == 'implemented_partial'


def test_trf2_marcado_como_requer_credencial_apos_correcao():
    sources = official_precatorio_sources()
    trf2 = sources['trf2_precatorios']
    assert trf2['integration_status'] == 'requires_credentials'
    assert trf2['requires_credentials'] is True
    assert trf2['requires_certificate'] is True


def test_summary_bate_com_total_do_registry():
    sources = official_precatorio_sources()
    summary = official_precatorio_sources_summary()
    assert summary['total_sources'] == len(sources)
    assert sum(summary['by_integration_status'].values()) == len(sources)
    assert sum(summary['by_scope'].values()) == len(sources)


def test_summary_tem_significado_para_cada_status_usado():
    summary = official_precatorio_sources_summary()
    for status in summary['by_integration_status']:
        assert status in summary['status_meanings'], f'status sem explicação: {status}'
