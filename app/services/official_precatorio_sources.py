from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class OfficialSource:
    """Fonte oficial/institucional para precatórios, RPVs, LOA ou fila.

    O objetivo deste registro NÃO é prometer que todas as fontes tenham API pública.
    Ele explicita, fonte por fonte, o que pode ser consultado, quais campos costumam
    ser exigidos e qual é a próxima ação técnica segura: API, portal público,
    arquivo aberto ou credencial institucional.
    """

    key: str
    name: str
    scope: str
    source_type: str
    priority: int
    official_url: str
    requires_credentials: bool = False
    requires_login: bool = False
    requires_certificate: bool = False
    supports_search_types: tuple[str, ...] = ()
    required_fields: tuple[str, ...] = ()
    optional_fields: tuple[str, ...] = ()
    fields_returned: tuple[str, ...] = ()
    integration_status: str = 'mapped_only'
    reliability: str = 'official'
    legal_notes: str = ''
    implementation_notes: str = ''

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key, value in list(data.items()):
            if isinstance(value, tuple):
                data[key] = list(value)
        return data


COMMON_OFFICIAL_FIELDS = (
    'source',
    'tribunal',
    'ramo',
    'numero_processo',
    'numero_requisitorio',
    'numero_precatorio',
    'tipo_requisicao',
    'ano_orcamento',
    'entidade_devedora',
    'natureza',
    'valor_requisitado',
    'valor_atualizado_quando_disponivel',
    'data_expedicao',
    'data_envio_tribunal',
    'status',
    'posicao_fila',
    'data_pagamento',
    'banco_pagamento',
    'fonte_url',
    'raw',
)


OFFICIAL_PRECAT_SOURCE_REGISTRY: dict[str, OfficialSource] = {
    'sispreq_pdpj': OfficialSource(
        key='sispreq_pdpj',
        name='SisPreq/PDPJ-Br',
        scope='nacional',
        source_type='api_institucional',
        priority=10,
        official_url='https://docs.pdpj.jus.br/servicos-negociais/sispreq/',
        requires_credentials=True,
        requires_login=True,
        supports_search_types=('cnj', 'numero_processo', 'numero_requisitorio', 'precatorio_number', 'rpv_number'),
        required_fields=('credencial_pdpj_ou_convenio',),
        optional_fields=('tribunal', 'ano_orcamento', 'entidade_devedora', 'cpf', 'cnpj', 'name'),
        fields_returned=COMMON_OFFICIAL_FIELDS,
        integration_status='requires_institutional_credentials',
        legal_notes='Camada nacional correta, mas não presumir acesso público. Usar apenas com credenciais/convênio autorizados.',
        implementation_notes='Quando houver credencial, criar adapter OAuth2/Keycloak/PDPJ e normalizar para PrecatorioOfficialRecord.',
    ),
    'mpo_siop_precatorios_dados_abertos': OfficialSource(
        key='mpo_siop_precatorios_dados_abertos',
        name='MPO/SIOP - Dados Abertos de Precatórios Federais Expedidos',
        scope='federal_orcamentario',
        source_type='dados_abertos_csv',
        priority=9,
        official_url='https://www.gov.br/planejamento/pt-br/assuntos/orcamento/precatorios-content/painel-precatorios/dados-abertos',
        supports_search_types=('entidade_devedora',),
        required_fields=('entidade_devedora (nome ou trecho)', 'ano_orcamento'),
        optional_fields=('tipo_despesa',),
        fields_returned=('chave', 'exercicio', 'nome_tribunal', 'tribunal_expedidor', 'esfera_justica', 'data_ajuizamento', 'data_autuacao', 'tipo_despesa_label', 'entidade_devedora', 'natureza_despesa', 'tipo_causa', 'valor_original', 'valor_atualizado', 'fonte_url'),
        integration_status='implemented_partial',
        legal_notes=(
            'Nota Metodológica oficial do SOF/MPO confirma: por exigência da LDO, a base é transmitida '
            '"sem qualquer dado que possibilite a identificação dos respectivos beneficiários" — não tem '
            'CNJ nem nome de credor. Serve para confirmar entidade devedora + ano-orçamento, não para achar '
            'um precatório específico de uma pessoa.'
        ),
        implementation_notes=(
            'Conector app/connectors/mpo_siop_precatorios.py: baixa o CSV oficial por exercício '
            '(um arquivo por ano, 2007-2027, confirmado ao vivo), nomes de coluna copiados literalmente '
            'da Nota Metodológica oficial do SOF/MPO (alta confiança). Arquivos reais passam de 20MB — '
            'maiores que o limite da ferramenta de pesquisa usada para verificar, então o parser foi '
            'validado com CSV sintético usando essas colunas, não contra o arquivo real ainda.'
        ),
    ),
    'cjf_precatorios': OfficialSource(
        key='cjf_precatorios',
        name='CJF - Precatórios e RPVs da Justiça Federal',
        scope='federal',
        source_type='dashboard_portal_oficial',
        priority=9,
        official_url='https://www.cjf.jus.br/publico/rpvs_precatorios/',
        supports_search_types=('cnj', 'numero_requisitorio', 'numero_precatorio', 'rpv_number', 'ano_orcamento'),
        required_fields=('tribunal ou ano_orcamento ou numero_requisitorio',),
        optional_fields=('cpf', 'cnpj', 'name', 'entidade_devedora'),
        fields_returned=COMMON_OFFICIAL_FIELDS,
        integration_status='mapped_public_dashboard',
        legal_notes='Fonte oficial federal. Verificar se há endpoint/CSV por trás do painel antes de scraping.',
        implementation_notes='Mapear chamadas de rede do dashboard; se houver CSV/API pública, criar adapter com cache.',
    ),
    'loa_camara_uniao': OfficialSource(
        key='loa_camara_uniao',
        name='LOA Câmara/União - Precatórios por órgão orçamentário',
        scope='federal_orcamentario',
        source_type='arquivo_loa',
        priority=8,
        official_url='https://www2.camara.leg.br/orcamento-da-uniao/leis-orcamentarias',
        supports_search_types=('numero_precatorio', 'numero_requisitorio', 'ano_orcamento', 'tribunal'),
        required_fields=('ano_orcamento',),
        optional_fields=('tribunal', 'orgao_orcamentario', 'numero_precatorio', 'numero_requisitorio'),
        fields_returned=('ano_orcamento', 'incluido_na_loa', 'orgao_orcamentario', 'tribunal', 'arquivo_origem', 'fonte_url', 'raw'),
        integration_status='mapped_open_budget_files',
        legal_notes='Usar para confirmar inclusão orçamentária, não como substituto do processo/requisitório.',
        implementation_notes='Criar parser por exercício; indexar relatórios por TRF/órgão.',
    ),
    'trf1_precatorios': OfficialSource(
        key='trf1_precatorios',
        name='TRF1 - Consulta Processual/RPV/Precatórios, SIREA/e-PRECWEB',
        scope='federal_trf1',
        source_type='portal_html_e_sistemas',
        priority=10,
        official_url='https://processual.trf1.jus.br/consultaProcessual/',
        requires_login=False,
        supports_search_types=('cpf', 'cnpj', 'name', 'oab', 'cnj', 'numero_processo', 'numero_requisitorio', 'numero_precatorio', 'rpv_number'),
        required_fields=('search_key',),
        optional_fields=('uf', 'secao', 'ano_orcamento', 'entidade_devedora'),
        fields_returned=COMMON_OFFICIAL_FIELDS + ('banco_deposito', 'movimentacoes_pagamento'),
        integration_status='implemented_partial',
        legal_notes='Não burlar captcha/login/certificado. SIREA/e-PRECWEB podem exigir cadastro/certificado para funções restritas.',
        implementation_notes=(
            'Consulta por CNJ/número de processo IMPLEMENTADA e confirmada ao vivo '
            '(app/connectors/cjf_trf_precatorios.py, endpoint processual.trf1.jus.br/consultaProcessual/processo.php). '
            'CPF/CNPJ/nome/OAB têm formulário público confirmado, mas ainda não implementados aqui '
            '(parâmetros exatos do formulário não confirmados sem inspecionar o HTML bruto).'
        ),
    ),
    'trf2_precatorios': OfficialSource(
        key='trf2_precatorios',
        name='TRF2 - Precatórios/RPVs e sistemas e-Proc/Apolo',
        scope='federal_trf2',
        source_type='portal_html_restrito',
        priority=4,
        official_url='https://www10.trf2.jus.br/consultas/precatorio-e-rpv/',
        requires_credentials=True,
        requires_login=True,
        requires_certificate=True,
        supports_search_types=('cnj', 'numero_processo', 'numero_requisitorio', 'numero_precatorio', 'rpv_number'),
        required_fields=('numero_requisitorio_autuado', 'chave_do_processo'),
        optional_fields=('cpf', 'cnpj', 'name', 'ano_orcamento'),
        fields_returned=COMMON_OFFICIAL_FIELDS,
        integration_status='requires_credentials',
        legal_notes=(
            'Desde a Resolução TRF2-RSP-2024/00082, precatórios/RPVs do TRF2 correm em segredo de justiça. '
            'Dados de pagamento/extrato só ficam visíveis para advogado credenciado com certificado digital no e-Proc. '
            'Consulta pública residual exige "número do requisitório autuado" + "chave do processo", ambos só obtidos junto à Divisão de Precatórios ou pelo advogado — não é descobrível só com CPF.'
        ),
        implementation_notes='Não vale a pena automatizar sem convênio/certificado de advogado. Prioridade baixa.',
    ),
    'trf3_requisicoes_pagamento': OfficialSource(
        key='trf3_requisicoes_pagamento',
        name='TRF3 - Requisições de Pagamento',
        scope='federal_trf3',
        source_type='portal_html',
        priority=8,
        official_url='https://web.trf3.jus.br/consultas/internet/consultareqpag',
        supports_search_types=('cpf', 'cnpj', 'oab', 'numero_processo', 'numero_requisitorio', 'protocolo'),
        required_fields=('cpf/cnpj', 'mais_um_identificador: oab|processo|oficio|protocolo'),
        optional_fields=('ano_orcamento', 'tipo_requisicao'),
        fields_returned=COMMON_OFFICIAL_FIELDS,
        integration_status='public_form_to_implement',
        legal_notes='Consulta informativa, sem efeitos legais segundo o portal.',
        implementation_notes='Criar adapter com validação de campos obrigatórios antes de chamar o portal.',
    ),
    'trf4_precatorios': OfficialSource(
        key='trf4_precatorios',
        name='TRF4 - Precatórios/RPVs/eproc',
        scope='federal_trf4',
        source_type='portal_html',
        priority=7,
        official_url='https://www.trf4.jus.br/',
        supports_search_types=('cnj', 'numero_processo', 'numero_requisitorio', 'numero_precatorio', 'rpv_number'),
        required_fields=('mapear_fonte_oficial',),
        optional_fields=('cpf', 'cnpj', 'name', 'ano_orcamento'),
        fields_returned=COMMON_OFFICIAL_FIELDS,
        integration_status='source_mapping_required',
        implementation_notes='Mapear consulta pública eproc/precatorios do TRF4 antes de implementar.',
    ),
    'trf5_precatorios': OfficialSource(
        key='trf5_precatorios',
        name='TRF5 - Portal Precatórios/RPVs',
        scope='federal_trf5',
        source_type='portal_html',
        priority=8,
        official_url='https://rpvprecatorio.trf5.jus.br/',
        supports_search_types=('cpf', 'cnpj', 'oab', 'numero_sequencial', 'numero_processo_execucao', 'numero_processo_originario', 'numero_processo_trf5', 'numero_requisitorio'),
        required_fields=('search_key', 'tipo_consulta'),
        optional_fields=('uf', 'tipo_requisicao', 'periodo_autuacao', 'mostrar_valores_vinculados'),
        fields_returned=COMMON_OFFICIAL_FIELDS,
        integration_status='public_form_to_implement',
        implementation_notes='Portal informa vários tipos de busca; implementar com seleção explícita tipo_consulta.',
    ),
    'trf6_precatorios': OfficialSource(
        key='trf6_precatorios',
        name='TRF6 - Roteador PJe/TRF1 ou eproc/TRF6',
        scope='federal_trf6',
        source_type='roteador_portal_html',
        priority=8,
        official_url='https://portal.trf6.jus.br/rpv-e-precatorios/consulta-precatorio-e-rpv/',
        supports_search_types=('cnj', 'numero_processo', 'numero_requisitorio', 'numero_precatorio', 'rpv_number'),
        required_fields=('sistema_origem: pje|eproc',),
        optional_fields=('cpf', 'cnpj', 'name', 'ano_orcamento'),
        fields_returned=COMMON_OFFICIAL_FIELDS,
        integration_status='router_to_implement',
        implementation_notes='Se PJe, consultar TRF1; se eproc, consultar eproc TRF6.',
    ),
    'tjdft_sapre': OfficialSource(
        key='tjdft_sapre',
        name='TJDFT/SAPRE - Ranking e lista externa de precatórios',
        scope='estadual_distrital_df',
        source_type='portal_html',
        priority=10,
        official_url='https://sapre.tjdft.jus.br/sapre/public/lista_externa.xhtml',
        supports_search_types=('cpf', 'cnpj', 'numero_precatorio', 'entidade_devedora', 'ano_orcamento'),
        required_fields=('search_key ou entidade_devedora',),
        optional_fields=('natureza', 'situacao', 'ano_orcamento'),
        fields_returned=('ordem_classificacao', 'tribunal', 'numero_processo', 'numero_precatorio', 'entidade_devedora', 'data_cadastro', 'ano_orcamento', 'natureza', 'situacao', 'fonte_url', 'raw'),
        integration_status='public_form_to_implement',
        implementation_notes='Prioridade alta para DF: retorna ano-orçamento, natureza, situação e ordem de classificação.',
    ),
    'tjsp_precatorios': OfficialSource(
        key='tjsp_precatorios',
        name='TJSP - Precatórios pendentes e pagamentos',
        scope='estadual_sp',
        source_type='portal_html_arquivos',
        priority=6,
        official_url='https://www.tjsp.jus.br/Precatorios/Precatorios/ListaPendentes',
        supports_search_types=('numero_precatorio', 'entidade_devedora', 'ano_orcamento'),
        required_fields=('numero_precatorio ou entidade_devedora',),
        optional_fields=('cpf', 'cnpj', 'name', 'natureza'),
        fields_returned=COMMON_OFFICIAL_FIELDS,
        integration_status='public_lists_to_implement',
    ),
    'stf_precatorios': OfficialSource(
        key='stf_precatorios',
        name='STF - Precatórios/RPVs do tribunal superior quando aplicável',
        scope='tribunal_superior',
        source_type='portal_orcamentario_a_mapear',
        priority=5,
        official_url='https://portal.stf.jus.br/',
        supports_search_types=('cnj', 'numero_processo', 'numero_precatorio', 'numero_requisitorio'),
        required_fields=('mapear_fonte_oficial',),
        optional_fields=('ano_orcamento', 'orgao_orcamentario'),
        fields_returned=COMMON_OFFICIAL_FIELDS,
        integration_status='source_mapping_required',
        implementation_notes='Tribunais superiores entram como camada própria quando houver requisição/orçamento vinculado ao órgão.',
    ),
    'stj_precatorios': OfficialSource(
        key='stj_precatorios',
        name='STJ - Precatórios/RPVs de competência originária (arquivos oficiais XLSX)',
        scope='tribunal_superior',
        source_type='dados_abertos_xlsx',
        priority=8,
        official_url='https://www.stj.jus.br/sites/portalp/Processos/precatorios',
        requires_login=False,
        supports_search_types=('precatorio_number', 'requisitorio_number', 'rpv_number', 'cnj', 'numero_processo'),
        required_fields=('search_key',),
        optional_fields=('ano_orcamento',),
        fields_returned=('sequencial', 'classe', 'numero_processo', 'credor_nome', 'natureza', 'prioridade', 'valor', 'previsao_pagamento', 'entidade_devedora', 'ano_orcamento', 'ano_expedicao', 'categoria', 'fonte_url', 'linha_arquivo'),
        integration_status='implemented_partial',
        legal_notes='Página pública verificada ao vivo em 01/07/2026: XLSX/XLSM abertos, sem login/captcha. Expedidos por ano, proposta por exercício (ex.: PRCs-proposta-2027.xlsx), pendentes, pagos por mês, mapa anual.',
        implementation_notes=(
            'Conector app/connectors/stj_precatorios.py: descobre os arquivos dinamicamente na página '
            '(anos novos entram sozinhos, sem trava fixa de exercício), baixa e parseia com cabeçalho '
            'flexível. Modo offline via STJ_LOCAL_DIR. Parser validado com planilha sintética idêntica '
            'à estrutura observada em print real; validação contra arquivo real do STJ pendente '
            '(rede deste ambiente não alcança stj.jus.br). Campo não encontrado vem None, nunca inventado.'
        ),
    ),
    'tst_precatorios': OfficialSource(
        key='tst_precatorios',
        name='TST - Precatórios/RPVs trabalhistas do tribunal superior quando aplicável',
        scope='tribunal_superior',
        source_type='portal_orcamentario_a_mapear',
        priority=5,
        official_url='https://www.tst.jus.br/',
        supports_search_types=('cnj', 'numero_processo', 'numero_precatorio', 'numero_requisitorio'),
        required_fields=('mapear_fonte_oficial',),
        optional_fields=('ano_orcamento', 'orgao_orcamentario'),
        fields_returned=COMMON_OFFICIAL_FIELDS,
        integration_status='source_mapping_required',
    ),
    'stm_precatorios': OfficialSource(
        key='stm_precatorios',
        name='STM - Justiça Militar da União, quando aplicável',
        scope='tribunal_superior',
        source_type='portal_orcamentario_a_mapear',
        priority=2,
        official_url='https://www.stm.jus.br/',
        supports_search_types=('cnj', 'numero_processo'),
        required_fields=('mapear_fonte_oficial',),
        optional_fields=(),
        fields_returned=COMMON_OFFICIAL_FIELDS,
        integration_status='source_mapping_required',
        legal_notes='Justiça Militar da União trata majoritariamente de matéria penal militar; precatório cível é hipótese rara. Incluído por completude do escopo pedido, não por relevância comercial esperada.',
    ),
}


# ---------------------------------------------------------------------------
# Cobertura completa de tribunais: TJs estaduais/distrital e TRTs.
#
# Diferente das fontes acima (pesquisadas e verificadas — ver
# docs/MAPA_FONTES_PRECATORIO_FEDERAL.md para CJF/TRF1-6), estas entradas
# NÃO foram individualmente pesquisadas nesta rodada. Só o domínio
# institucional (.jus.br) é preenchido, por ser convenção pública estável.
# Todo o resto fica None/vazio e o status é 'not_researched' de propósito —
# para não inventar se aceita CPF, se tem captcha, se retorna LOA etc. sem
# ter checado. Registrar 80 tribunais de uma vez sem isso seria inventar dado.
# ---------------------------------------------------------------------------

def _unresearched_court(key: str, name: str, scope: str, url: str, note: str) -> OfficialSource:
    return OfficialSource(
        key=key,
        name=name,
        scope=scope,
        source_type='a_pesquisar',
        priority=1,
        official_url=url,
        supports_search_types=(),
        required_fields=(),
        optional_fields=(),
        fields_returned=(),
        integration_status='not_researched',
        legal_notes=note,
        implementation_notes='Domínio institucional confirmado por convenção pública (.jus.br), não verificado individualmente. Pesquisar antes de qualquer implementação.',
    )


_STATE_COURTS = [
    ('tjac', 'TJAC - Tribunal de Justiça do Acre', 'https://www.tjac.jus.br'),
    ('tjal', 'TJAL - Tribunal de Justiça de Alagoas', 'https://www.tjal.jus.br'),
    ('tjam', 'TJAM - Tribunal de Justiça do Amazonas', 'https://www.tjam.jus.br'),
    ('tjap', 'TJAP - Tribunal de Justiça do Amapá', 'https://www.tjap.jus.br'),
    ('tjba', 'TJBA - Tribunal de Justiça da Bahia', 'https://www.tjba.jus.br'),
    ('tjce', 'TJCE - Tribunal de Justiça do Ceará', 'https://www.tjce.jus.br'),
    ('tjes', 'TJES - Tribunal de Justiça do Espírito Santo', 'https://www.tjes.jus.br'),
    ('tjgo', 'TJGO - Tribunal de Justiça de Goiás', 'https://www.tjgo.jus.br'),
    ('tjma', 'TJMA - Tribunal de Justiça do Maranhão', 'https://www.tjma.jus.br'),
    ('tjmg', 'TJMG - Tribunal de Justiça de Minas Gerais', 'https://www.tjmg.jus.br'),
    ('tjms', 'TJMS - Tribunal de Justiça de Mato Grosso do Sul', 'https://www.tjms.jus.br'),
    ('tjmt', 'TJMT - Tribunal de Justiça de Mato Grosso', 'https://www.tjmt.jus.br'),
    ('tjpa', 'TJPA - Tribunal de Justiça do Pará', 'https://www.tjpa.jus.br'),
    ('tjpb', 'TJPB - Tribunal de Justiça da Paraíba', 'https://www.tjpb.jus.br'),
    ('tjpe', 'TJPE - Tribunal de Justiça de Pernambuco', 'https://www.tjpe.jus.br'),
    ('tjpi', 'TJPI - Tribunal de Justiça do Piauí', 'https://www.tjpi.jus.br'),
    ('tjpr', 'TJPR - Tribunal de Justiça do Paraná', 'https://www.tjpr.jus.br'),
    ('tjrj', 'TJRJ - Tribunal de Justiça do Rio de Janeiro', 'https://www.tjrj.jus.br'),
    ('tjrn', 'TJRN - Tribunal de Justiça do Rio Grande do Norte', 'https://www.tjrn.jus.br'),
    ('tjro', 'TJRO - Tribunal de Justiça de Rondônia', 'https://www.tjro.jus.br'),
    ('tjrr', 'TJRR - Tribunal de Justiça de Roraima', 'https://www.tjrr.jus.br'),
    ('tjrs', 'TJRS - Tribunal de Justiça do Rio Grande do Sul', 'https://www.tjrs.jus.br'),
    ('tjsc', 'TJSC - Tribunal de Justiça de Santa Catarina', 'https://www.tjsc.jus.br'),
    ('tjse', 'TJSE - Tribunal de Justiça de Sergipe', 'https://www.tjse.jus.br'),
    ('tjto', 'TJTO - Tribunal de Justiça do Tocantins', 'https://www.tjto.jus.br'),
]
for _key, _name, _url in _STATE_COURTS:
    OFFICIAL_PRECAT_SOURCE_REGISTRY[_key] = _unresearched_court(
        _key, _name, 'estadual', _url,
        'Justiça estadual. TJDFT e TJSP já têm entrada própria pesquisada (tjdft_sapre, tjsp_precatorios); os demais TJs ainda não.',
    )


_LABOR_COURTS = [
    ('trt1', 'TRT1 - Tribunal Regional do Trabalho (RJ)', 'https://www.trt1.jus.br'),
    ('trt2', 'TRT2 - Tribunal Regional do Trabalho (SP - Capital/Grande SP)', 'https://www.trt2.jus.br'),
    ('trt3', 'TRT3 - Tribunal Regional do Trabalho (MG)', 'https://www.trt3.jus.br'),
    ('trt4', 'TRT4 - Tribunal Regional do Trabalho (RS)', 'https://www.trt4.jus.br'),
    ('trt5', 'TRT5 - Tribunal Regional do Trabalho (BA)', 'https://www.trt5.jus.br'),
    ('trt6', 'TRT6 - Tribunal Regional do Trabalho (PE)', 'https://www.trt6.jus.br'),
    ('trt7', 'TRT7 - Tribunal Regional do Trabalho (CE)', 'https://www.trt7.jus.br'),
    ('trt8', 'TRT8 - Tribunal Regional do Trabalho (PA/AP)', 'https://www.trt8.jus.br'),
    ('trt9', 'TRT9 - Tribunal Regional do Trabalho (PR)', 'https://www.trt9.jus.br'),
    ('trt10', 'TRT10 - Tribunal Regional do Trabalho (DF/TO)', 'https://www.trt10.jus.br'),
    ('trt11', 'TRT11 - Tribunal Regional do Trabalho (AM/RR)', 'https://www.trt11.jus.br'),
    ('trt12', 'TRT12 - Tribunal Regional do Trabalho (SC)', 'https://www.trt12.jus.br'),
    ('trt13', 'TRT13 - Tribunal Regional do Trabalho (PB)', 'https://www.trt13.jus.br'),
    ('trt14', 'TRT14 - Tribunal Regional do Trabalho (RO/AC)', 'https://www.trt14.jus.br'),
    ('trt15', 'TRT15 - Tribunal Regional do Trabalho (Campinas/interior SP)', 'https://www.trt15.jus.br'),
    ('trt16', 'TRT16 - Tribunal Regional do Trabalho (MA)', 'https://www.trt16.jus.br'),
    ('trt17', 'TRT17 - Tribunal Regional do Trabalho (ES)', 'https://www.trt17.jus.br'),
    ('trt18', 'TRT18 - Tribunal Regional do Trabalho (GO)', 'https://www.trt18.jus.br'),
    ('trt19', 'TRT19 - Tribunal Regional do Trabalho (AL)', 'https://www.trt19.jus.br'),
    ('trt20', 'TRT20 - Tribunal Regional do Trabalho (SE)', 'https://www.trt20.jus.br'),
    ('trt21', 'TRT21 - Tribunal Regional do Trabalho (RN)', 'https://www.trt21.jus.br'),
    ('trt22', 'TRT22 - Tribunal Regional do Trabalho (PI)', 'https://www.trt22.jus.br'),
    ('trt23', 'TRT23 - Tribunal Regional do Trabalho (MT)', 'https://www.trt23.jus.br'),
    ('trt24', 'TRT24 - Tribunal Regional do Trabalho (MS)', 'https://www.trt24.jus.br'),
]
for _key, _name, _url in _LABOR_COURTS:
    OFFICIAL_PRECAT_SOURCE_REGISTRY[_key] = _unresearched_court(
        _key, _name, 'trabalhista', _url,
        'Justiça do Trabalho. Precatórios trabalhistas seguem regras próprias (RPV/precatório da Fazenda Pública em execução trabalhista) — não pesquisado ainda.',
    )

OFFICIAL_PRECAT_SOURCE_REGISTRY['csjt_precatorios'] = _unresearched_court(
    'csjt_precatorios', 'CSJT - Conselho Superior da Justiça do Trabalho', 'nacional_trabalhista',
    'https://www.csjt.jus.br',
    'Papel provável análogo ao CJF (orçamentário/regulatório), mas para a Justiça do Trabalho. Não pesquisado ainda.',
)


FEDERAL_TRF_SOURCE_KEYS = (
    'trf1_precatorios',
    'trf2_precatorios',
    'trf3_requisicoes_pagamento',
    'trf4_precatorios',
    'trf5_precatorios',
    'trf6_precatorios',
)


def official_precatorio_sources() -> dict[str, dict[str, Any]]:
    return {key: source.as_dict() for key, source in OFFICIAL_PRECAT_SOURCE_REGISTRY.items()}


def official_precatorio_sources_summary() -> dict[str, Any]:
    """Resumo por status/escopo, para painel e para /api/official-precatorio/sources.

    Não esconde nenhuma fonte não implementada — só agrupa por status real,
    exatamente para que o painel possa mostrar 'implementado' vs 'mapeado' vs
    'requer credencial' vs 'a pesquisar' sem inventar progresso que não existe.
    """
    by_status: dict[str, int] = {}
    by_scope: dict[str, int] = {}
    for source in OFFICIAL_PRECAT_SOURCE_REGISTRY.values():
        by_status[source.integration_status] = by_status.get(source.integration_status, 0) + 1
        by_scope[source.scope] = by_scope.get(source.scope, 0) + 1
    return {
        'total_sources': len(OFFICIAL_PRECAT_SOURCE_REGISTRY),
        'by_integration_status': dict(sorted(by_status.items(), key=lambda kv: -kv[1])),
        'by_scope': dict(sorted(by_scope.items(), key=lambda kv: -kv[1])),
        'status_meanings': {
            'implemented_partial': 'Tem consulta real implementada e testada para parte dos tipos de busca.',
            'mapped_public_dashboard': 'Painel público institucional mapeado (informativo, geralmente sem busca própria por identificador).',
            'mapped_open_budget_files': 'Fonte orçamentária mapeada, com relatórios/arquivos disponíveis por exercício.',
            'public_open_data_to_implement': 'Fonte pública/dados abertos mapeada, implementação de download/indexação ainda pendente.',
            'public_form_to_implement': 'Formulário público de busca mapeado, conector de consulta ainda não implementado.',
            'public_portal_to_implement': 'Portal público sem login mapeado, conector de consulta ainda não implementado.',
            'public_lists_to_implement': 'Fonte pública com listas/relatórios mapeada, conector ainda não implementado.',
            'router_to_implement': 'Não tem sistema próprio: só decide para qual outra fonte encaminhar a consulta.',
            'requires_institutional_credentials': 'Exige credencial/convênio institucional (ex.: PDPJ). Não presumir acesso público.',
            'requires_credentials': 'Exige login e/ou certificado digital para os dados relevantes (ex.: segredo de justiça).',
            'source_mapping_required': 'Fonte identificada, mas ainda falta mapear o caminho técnico exato de consulta.',
            'not_researched': 'Só o domínio institucional foi registrado. Nenhuma pesquisa de capacidades foi feita ainda.',
        },
    }


def sources_for_search(search_type: str, extra_params: dict[str, Any] | None = None) -> list[OfficialSource]:
    extra_params = extra_params or {}
    tribunal = str(extra_params.get('tribunal') or extra_params.get('trf') or '').lower()
    uf = str(extra_params.get('uf') or '').upper()

    candidates: list[OfficialSource] = []
    for source in OFFICIAL_PRECAT_SOURCE_REGISTRY.values():
        if search_type in source.supports_search_types or search_type in {'cnj', 'numero_processo'}:
            if tribunal and tribunal.replace(' ', '') not in source.key.lower() and tribunal not in source.scope.lower():
                # Mantém fontes nacionais/orçamentárias mesmo com tribunal específico.
                if source.scope not in {'nacional', 'federal_orcamentario', 'federal'}:
                    continue
            if uf == 'DF' and source.key in {'tjsp_precatorios'}:
                continue
            candidates.append(source)

    return sorted(candidates, key=lambda src: (-src.priority, src.key))


def build_precatorio_route_plan(search_type: str, search_key: str, extra_params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Plano de camadas para chegar ao precatório/LOA.

    Esta função explica exatamente quais buscas devem acontecer e quais dados
    faltam. Ela é deliberadamente conservadora: quando uma fonte exige credencial,
    login, certificado ou mapeamento, isso aparece no plano em vez de inventar dado.
    """
    extra_params = extra_params or {}
    matched_sources = sources_for_search(search_type, extra_params)

    missing: list[str] = []
    if search_type in {'oab'} and not extra_params.get('uf'):
        missing.append('UF (estado da OAB)')
    if search_type in {'numero_requisitorio', 'requisitorio_number', 'numero_precatorio', 'precatorio_number', 'rpv_number'} and not (extra_params.get('tribunal') or extra_params.get('trf')):
        missing.append('tribunal (qual TRF/TJ)')
    if 'ano_orcamento' not in extra_params and search_type in {'numero_precatorio', 'precatorio_number', 'ano_orcamento'}:
        missing.append('ano-orçamento (exercício da LOA), quando a pergunta for sobre orçamento')

    layers = [
        {
            'layer': 'descoberta_processual',
            'goal': 'Encontrar processos relacionados ao identificador informado.',
            'sources': ['datajud', 'judit/escavador/jusbrasil se houver token', 'MNI/PJe/eproc se houver credencial'],
            'expected_output': ['numero_processo', 'classe', 'assunto', 'partes', 'movimentacoes', 'indicio_precatorio_rpv'],
        },
        {
            'layer': 'localizacao_requisitorio',
            'goal': 'A partir do processo, localizar número do requisitório/precatório/RPV.',
            'sources': [src.key for src in matched_sources if src.scope in {'nacional', 'federal', 'federal_trf1', 'federal_trf2', 'federal_trf3', 'federal_trf4', 'federal_trf5', 'federal_trf6', 'estadual_distrital_df', 'estadual_sp'}][:8],
            'expected_output': ['numero_requisitorio', 'numero_precatorio', 'tipo_requisicao', 'data_expedicao', 'data_envio_tribunal'],
        },
        {
            'layer': 'loa_orcamento',
            'goal': 'Confirmar exercício orçamentário, PLOA/LOA e órgão orçamentário.',
            'sources': ['mpo_siop_precatorios_dados_abertos', 'loa_camara_uniao', 'cjf_precatorios', 'TRF1-TRF6 quando federal', 'LOA estadual/distrital quando estadual'],
            'expected_output': ['ano_orcamento', 'incluido_na_loa', 'orgao_orcamentario', 'arquivo_origem', 'fonte_url'],
        },
        {
            'layer': 'fila_pagamento_status',
            'goal': 'Buscar situação, ordem cronológica, pagamento e banco quando disponível.',
            'sources': [src.key for src in matched_sources if src.integration_status != 'source_mapping_required'][:8],
            'expected_output': ['status', 'posicao_fila', 'data_pagamento', 'banco_pagamento', 'situacao'],
        },
        {
            'layer': 'calculo_oportunidade',
            'goal': 'Projetar valor, risco e oportunidade comercial depois de obter valor/data-base.',
            'sources': ['BCB/SGS', 'IBGE/SIDRA', 'tabelas/regra por tribunal', 'modelo comercial MeuPrecatórioBR'],
            'expected_output': ['valor_atualizado', 'data_base', 'preco_sugerido', 'risco', 'proxima_acao'],
        },
    ]

    return {
        'input': {'search_type': search_type, 'search_key': search_key, 'extra_params': extra_params},
        'missing_recommended_fields': missing,
        'route_layers': layers,
        'candidate_sources': [src.as_dict() for src in matched_sources],
        'disclaimer': 'Plano de busca. Resultados reais dependem de token, credencial, portal público, arquivo aberto ou implementação específica da fonte.',
    }
