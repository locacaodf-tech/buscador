"""Testes da resolução da chave do DataJud: usuário tem prioridade, fallback
público nunca falha, e a chave completa nunca aparece em nenhuma resposta."""
from app.config import (
    Settings,
    DEFAULT_DATAJUD_PUBLIC_API_KEY,
    resolved_datajud_api_key,
    datajud_key_source,
    mask_api_key,
)
from app.connectors.datajud import DataJudConnector
from app.services.source_master import external_sources


def test_sem_chave_do_usuario_usa_fallback_publico():
    settings = Settings(datajud_api_key='')
    assert resolved_datajud_api_key(settings) == DEFAULT_DATAJUD_PUBLIC_API_KEY
    assert datajud_key_source(settings) == 'chave_publica_padrao'


def test_com_chave_do_usuario_usa_a_dele_nao_o_fallback():
    settings = Settings(datajud_api_key='minha-chave-propria-xyz')
    assert resolved_datajud_api_key(settings) == 'minha-chave-propria-xyz'
    assert datajud_key_source(settings) == 'configurado_pelo_usuario'


def test_conector_datajud_nunca_falha_por_falta_de_chave():
    """Antes desta correção, o conector levantava ProviderNotConfigured sem
    chave configurada. Agora sempre inicializa, com fallback público."""
    connector = DataJudConnector()
    assert connector.api_key  # nunca vazio
    assert 'APIKey' in connector.headers['Authorization']


def test_mask_api_key_nunca_devolve_a_chave_completa():
    chave = DEFAULT_DATAJUD_PUBLIC_API_KEY
    mascarada = mask_api_key(chave)
    assert mascarada != chave
    assert chave not in mascarada
    assert len(mascarada) < len(chave)


def test_mask_api_key_com_valor_curto_ou_vazio():
    assert mask_api_key('') == '***'
    assert mask_api_key('abc') == '***'


def test_fontes_expoe_status_da_chave_sem_expor_o_valor():
    sources = external_sources()
    datajud = sources['datajud_cnj']
    assert datajud['chave_em_uso'] in {'configurado_pelo_usuario', 'chave_publica_padrao'}
    # nunca a chave completa em nenhum campo do dicionario
    for value in datajud.values():
        assert DEFAULT_DATAJUD_PUBLIC_API_KEY not in str(value)
