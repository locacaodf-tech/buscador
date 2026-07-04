import os

from fastapi.testclient import TestClient

os.environ.setdefault('APP_LOGIN_PASSWORD', '')
os.environ.setdefault('INTERNAL_API_TOKEN', '')

from app.main import app  # noqa: E402
from app.services.source_master import (  # noqa: E402
    EXTERNAL_SOURCE_REGISTRY,
    external_sources,
    master_sources_summary,
)

client = TestClient(app)


def test_registry_externo_tem_fontes_esperadas():
    esperadas = {
        'datajud_cnj', 'judit_api', 'comunica_pje_djen', 'mni_pje', 'sispreq_pdpj',
        'codex_cnj', 'bnmp', 'antecedentes_criminais_pf_sinic',
        'escavador_api', 'jusbrasil_api', 'infosimples_apis',
    }
    assert esperadas == set(EXTERNAL_SOURCE_REGISTRY)


def test_datajud_e_judit_marcados_como_implementados():
    sources = external_sources()
    assert sources['datajud_cnj']['integration_status'] == 'implemented'
    assert sources['judit_api']['integration_status'] == 'implemented'


def test_comunica_pje_marcado_como_institucional_nao_publico():
    sources = external_sources()
    comunica = sources['comunica_pje_djen']
    assert comunica['requires_credentials'] is True
    assert 'tribunais' in comunica['notes'].lower()


def test_antecedentes_criminais_marca_captcha_confirmado():
    sources = external_sources()
    ant = sources['antecedentes_criminais_pf_sinic']
    assert ant['captcha_expected'] is True
    assert ant['integration_status'] == 'captcha_detected'


def test_fontes_nao_pesquisadas_nao_inventam_dado():
    sources = external_sources()
    for key in ['codex_cnj', 'bnmp', 'escavador_api', 'jusbrasil_api', 'infosimples_apis']:
        assert sources[key]['integration_status'] == 'not_researched'
        assert not sources[key]['accepted_inputs']  # tupla vazia -> nenhuma capacidade inventada


def test_summary_agrega_os_tres_registries():
    summary = master_sources_summary()
    assert summary['total_precatorio_oficial'] == 66
    assert summary['total_certidoes'] == 34  # 26 TJs estaduais + TJDFT + 7 fontes fixas (Serpro/Regularize/CJF/STF/STJ/TST/TRT-base)
    assert summary['total_externo_comercial'] == 11
    assert any('datajud_cnj' in e['source'] or 'judit_api' in e['source'] for e in summary['prontos_para_uso_agora'])


def test_summary_lista_o_que_precisa_de_credencial():
    summary = master_sources_summary()
    fontes = [e['source'] for e in summary['dependem_de_credencial_ou_contrato']]
    assert any('sispreq' in f for f in fontes)
    # Serpro é 'implemented_configurable' (o código já existe, só falta credencial) ->
    # aparece em prontos_para_uso_agora, não aqui. Confirma essa distinção.
    prontos = [e['source'] for e in summary['prontos_para_uso_agora']]
    assert any('serpro' in f for f in prontos)


def test_endpoint_sources_agrega_tudo():
    resp = client.get('/api/sources')
    assert resp.status_code == 200
    data = resp.json()
    assert 'precatorio_oficial' in data
    assert 'certidoes' in data
    assert 'externo_comercial' in data
    assert data['summary']['total_precatorio_oficial'] == 66
