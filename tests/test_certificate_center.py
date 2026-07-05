import asyncio
import os

from fastapi.testclient import TestClient

os.environ.setdefault('APP_LOGIN_PASSWORD', '')
os.environ.setdefault('INTERNAL_API_TOKEN', '')

from app.main import app  # noqa: E402
from app.db import init_db  # noqa: E402
init_db()  # TestClient em nível de módulo não dispara o startup event; cria as tabelas explicitamente

from app.services.certificate_center import (  # noqa: E402
    CERTIFICATE_SOURCE_REGISTRY,
    CertificateStatus,
    build_certificate_plan,
    request_certificate,
    request_serpro_cnd,
    serpro_tipo_contribuinte,
)


client = TestClient(app)


def test_registry_tem_todas_as_fontes_pedidas():
    tjs_estaduais = {
        'tjac_certidoes', 'tjal_certidoes', 'tjap_certidoes', 'tjam_certidoes', 'tjba_certidoes',
        'tjce_certidoes', 'tjes_certidoes', 'tjgo_certidoes', 'tjma_certidoes', 'tjmt_certidoes',
        'tjms_certidoes', 'tjmg_certidoes', 'tjpa_certidoes', 'tjpb_certidoes', 'tjpr_certidoes',
        'tjpe_certidoes', 'tjpi_certidoes', 'tjrj_certidoes', 'tjrn_certidoes', 'tjrs_certidoes',
        'tjro_certidoes', 'tjrr_certidoes', 'tjsc_certidoes', 'tjsp_certidoes', 'tjse_certidoes',
        'tjto_certidoes',
    }
    assert len(tjs_estaduais) == 26  # 26 estados (DF fica em outra camada, é distrital não estadual)
    esperadas = tjs_estaduais | {
        'receita_pgfn_cnd_portal', 'serpro_consulta_cnd', 'cjf_certidao_unificada', 'tjdft_certidoes',
        'stf_certidoes', 'stj_certidoes', 'tst_certidoes', 'trt_certidoes_base',
    }
    assert esperadas == set(CERTIFICATE_SOURCE_REGISTRY)


def test_tjpe_marcado_com_captcha_classico_confirmado():
    tjpe = CERTIFICATE_SOURCE_REGISTRY['tjpe_certidoes']
    assert tjpe.captcha_expected is True
    assert 'captcha_relay' in tjpe.notes


def test_tjba_marcado_como_bloqueado_por_robots_txt():
    tjba = CERTIFICATE_SOURCE_REGISTRY['tjba_certidoes']
    assert 'robots.txt' in tjba.notes


def test_tjsc_marcado_como_exigindo_gov_br():
    tjsc = CERTIFICATE_SOURCE_REGISTRY['tjsc_certidoes']
    assert tjsc.requires_login is True
    assert 'gov.br' in tjsc.notes


def test_tjsp_aponta_para_cadastro_de_pedido_nao_para_faq():
    """Bug real encontrado pelo usuário: o link apontava pra página de
    Perguntas Frequentes em vez do formulário de pedido de certidão."""
    tjsp = CERTIFICATE_SOURCE_REGISTRY['tjsp_certidoes']
    assert 'DuvidasFrequentes' not in tjsp.official_url
    assert 'CertidoesPrimeiraInstancia' in tjsp.official_url
    assert tjsp.requires_login is False  # a 1ª instância (esse link) é gratuita, sem gov.br


def test_fontes_nao_pesquisadas_declaram_isso():
    for source in CERTIFICATE_SOURCE_REGISTRY.values():
        if source.integration_status == 'not_researched':
            notas = source.notes.lower()
            assert 'pesquisad' in notas or 'verificad' in notas, f'{source.source_id} não explica que falta pesquisa'


def test_serpro_tipo_contribuinte():
    assert serpro_tipo_contribuinte('123.456.789-00') == 2  # CPF
    assert serpro_tipo_contribuinte('00.394.460/0005-41') == 1  # CNPJ
    assert serpro_tipo_contribuinte('123') is None


def test_serpro_sem_credenciais_responde_requer_api_contratada():
    result = asyncio.run(request_serpro_cnd('12345678900'))
    assert result['status'] == CertificateStatus.REQUER_API_CONTRATADA
    # Achado real da auditoria: a mensagem vazava nome de variável de ambiente
    # (SERPRO_CND_CONSUMER_KEY/SECRET) e o link principal apontava pra Loja
    # Serpro (contratação paga) em vez do Regularize (emissão manual grátis).
    assert 'SERPRO_CND_CONSUMER' not in result['message']
    assert '.env' not in result['message']
    assert result['fonte_url'] == 'https://www.regularize.pgfn.gov.br/'
    assert result['fonte_url_secundaria'] == 'https://loja.serpro.gov.br/consultacnd'
    assert 'automação futura' in result['fonte_url_secundaria_label'].lower()


def test_fonte_nao_pesquisada_nunca_emite_certidao():
    result = asyncio.run(request_certificate('stf_certidoes', 'civel', '12345678900', None))
    assert result['status'] == CertificateStatus.NAO_INTEGRADO
    assert result['status'] not in {CertificateStatus.NEGATIVA, CertificateStatus.POSITIVA}


def test_tipo_de_certidao_incompativel_da_erro_claro():
    result = asyncio.run(request_certificate('serpro_consulta_cnd', 'criminal', '12345678900', None))
    assert result['status'] == CertificateStatus.ERRO
    assert 'não emite' in result['message']


def test_fonte_desconhecida():
    result = asyncio.run(request_certificate('nao_existe', 'civel', None, None))
    assert result['status'] == CertificateStatus.ERRO


def test_plan_filtra_por_tipo():
    plan = build_certificate_plan('12345678900', ['fiscal_cnd'])
    ids = {s['source_id'] for s in plan['steps']}
    assert 'serpro_consulta_cnd' in ids
    assert 'stf_certidoes' not in ids
    assert plan['document_masked'] is not None
    assert '123' not in plan['document_masked'] or '*' in plan['document_masked']


def test_plan_marca_serpro_como_pronto_para_executar():
    plan = build_certificate_plan(None, ['fiscal_cnd'])
    serpro = next(s for s in plan['steps'] if s['source_id'] == 'serpro_consulta_cnd')
    assert serpro['ready_to_execute'] is True
    assert 'requer contrato de API (Serpro)' in serpro['blockers']


# ---------- Endpoints end-to-end ----------

def test_endpoint_sources():
    resp = client.get('/api/certificates/sources')
    assert resp.status_code == 200
    assert 'serpro_consulta_cnd' in resp.json()['sources']


def test_endpoint_plan():
    resp = client.post('/api/certificates/plan', json={'document': '12345678900', 'certificate_types': ['civel']})
    assert resp.status_code == 200
    ids = {s['source_id'] for s in resp.json()['steps']}
    assert 'cjf_certidao_unificada' in ids


def test_endpoint_request_e_get_por_id():
    resp = client.post('/api/certificates/request', json={
        'source_id': 'serpro_consulta_cnd', 'certificate_type': 'fiscal_cnd', 'document': '12345678900',
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data['status'] == 'requer_api_contratada'
    cert_id = data['id']

    got = client.get(f'/api/certificates/{cert_id}')
    assert got.status_code == 200
    stored = got.json()
    assert stored['status'] == 'requer_api_contratada'
    assert stored['document_masked'] is not None
    assert '12345678900' not in str(stored)  # documento nunca armazenado em claro


def test_endpoint_get_id_inexistente():
    resp = client.get('/api/certificates/999999')
    assert resp.status_code == 404


def test_nunca_nada_consta_sem_documento_real():
    """Regra do produto: 'negativa' só com documento/código real. Nenhuma
    fonte atual pode produzir isso (Serpro sem credencial, resto não
    integrado) — logo nenhum request pode retornar negativa/positiva."""
    for source_id, source in CERTIFICATE_SOURCE_REGISTRY.items():
        for cert_type in source.certificate_types:
            result = asyncio.run(request_certificate(source_id, cert_type, '12345678900', 'Teste'))
            assert result['status'] not in {'negativa', 'positiva', 'positiva_efeito_negativa'}, (
                f'{source_id}/{cert_type} emitiu certidão sem documento real!'
            )


def test_tribunais_pesquisados_tem_campos_estruturados():
    """Os TJs onde de fato pesquisei os campos do formulário (turno anterior)
    precisam ter accepted_inputs preenchido, não só prosa em notes — é isso
    que permite a tela desenhar o formulário certo por tribunal."""
    tribunais_com_campos_confirmados = [
        'tjmg_certidoes', 'tjsp_certidoes', 'tjrj_certidoes', 'tjpe_certidoes',
        'tjce_certidoes', 'tjgo_certidoes', 'tjpr_certidoes', 'tjrs_certidoes', 'tjsc_certidoes',
    ]
    for key in tribunais_com_campos_confirmados:
        source = CERTIFICATE_SOURCE_REGISTRY[key]
        assert len(source.accepted_inputs) > 0, f'{key} deveria ter accepted_inputs preenchido'


def test_tjpe_pede_titulo_eleitor_tjsp_pede_naturalidade():
    """Confirma que os campos são específicos por tribunal, não um padrão único copiado."""
    tjpe = CERTIFICATE_SOURCE_REGISTRY['tjpe_certidoes']
    tjsp = CERTIFICATE_SOURCE_REGISTRY['tjsp_certidoes']
    tjmg = CERTIFICATE_SOURCE_REGISTRY['tjmg_certidoes']
    assert 'titulo_eleitor' in tjpe.accepted_inputs
    assert 'naturalidade' in tjsp.accepted_inputs
    assert 'titulo_eleitor' not in tjmg.accepted_inputs
    assert len(tjmg.accepted_inputs) < len(tjsp.accepted_inputs)  # TJMG pede bem menos campos que TJSP


def test_mensagem_de_fonte_nao_integrada_nunca_vaza_nota_de_pesquisa_interna():
    """Bug real reportado pelo usuário (print de tela): a mensagem incluía os
    primeiros 180 caracteres de source.notes cru, o que vazou anotação de
    pesquisa interna ('MELHOR ALVO REAL PARA O captcha_relay.py...') direto
    pra tela do usuário. A mensagem agora é genérica/consciente de captcha e
    nunca usa source.notes."""
    import asyncio
    resultado = asyncio.run(request_certificate('tjpe_certidoes', 'civel', '25683919000158', None))
    assert 'captcha_relay' not in resultado['message']
    assert 'MELHOR ALVO' not in resultado['message']
    assert resultado['status'] == CertificateStatus.CAPTCHA_DETECTADO
    assert resultado['message'] == (
        'O portal do TJPE exige captcha/validação manual. Por enquanto, emita '
        'manualmente pelo link oficial. Depois, registre o resultado como '
        'evidência manual.'
    )
