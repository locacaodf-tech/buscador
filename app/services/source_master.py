from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from .official_precatorio_sources import official_precatorio_sources, official_precatorio_sources_summary
from .certificate_center import certificate_sources


@dataclass
class ExternalSource:
    """Fontes que não são 'precatório oficial' nem 'certidão' — APIs
    processuais nacionais/institucionais e provedores comerciais."""

    source_id: str
    name: str
    category: str  # api_publica, api_institucional, api_privada_comercial
    scope: str
    url_documentacao: str
    accepted_inputs: tuple[str, ...] = ()
    requires_credentials: bool = False
    requires_contract: bool = False
    captcha_expected: bool | None = None
    integration_status: str = 'not_researched'
    notes: str = ''

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# Pesquisado ao vivo em 01-02/07/2026. Fontes já implementadas como conectores
# reais (datajud, judit) apontam para isso explicitamente — não duplicam lógica,
# só documentam no mesmo lugar que o resto.
EXTERNAL_SOURCE_REGISTRY: dict[str, ExternalSource] = {
    'datajud_cnj': ExternalSource(
        source_id='datajud_cnj',
        name='DataJud/CNJ - API Pública',
        category='api_publica',
        scope='nacional_processual',
        url_documentacao='https://www.cnj.jus.br/sistemas/datajud/api-publica/',
        accepted_inputs=('cnj', 'numero_processo'),
        integration_status='implemented',
        notes='Já implementado (app/connectors/datajud.py). Metadados processuais públicos de todo o Brasil; não resolve CPF/nome nem precatório/LOA oficial.',
    ),
    'judit_api': ExternalSource(
        source_id='judit_api',
        name='Judit API',
        category='api_privada_comercial',
        scope='nacional_processual',
        url_documentacao='https://produto.judit.io/api',
        accepted_inputs=('cpf', 'cnpj', 'oab', 'name', 'cnj'),
        requires_contract=True,
        integration_status='implemented',
        notes='Já implementado (app/connectors/judit.py). Funciona quando JUDIT_ENABLED=true + JUDIT_API_KEY configurados.',
    ),
    'comunica_pje_djen': ExternalSource(
        source_id='comunica_pje_djen',
        name='Comunica/PJe (DJEN) - publicações e comunicações processuais',
        category='api_institucional',
        scope='nacional_processual',
        url_documentacao='https://www.cnj.jus.br/programas-e-acoes/processo-judicial-eletronico-pje/comunicacoes-processuais/orientacoes-aos-tribunais/',
        accepted_inputs=(),
        requires_credentials=True,
        integration_status='requires_institutional_credentials',
        notes=(
            'CONFIRMADO ao vivo, e é mais restrito do que o texto que você colou sugeria: a API '
            '(comunicaapi.pje.jus.br) é para TRIBUNAIS enviarem publicações — exige usuário/senha do '
            'sistema Corporativo do CNJ, liberado por Administrador Regional do tribunal. Não é uma API '
            'pública de busca para terceiros. Existe um site público de busca de comunicações '
            '(comunica.pje.jus.br), mas não confirmei uma API de leitura pública por trás dele nesta rodada '
            '— precisa mapear separadamente se for útil pra você monitorar publicações.'
        ),
    ),
    'mni_pje': ExternalSource(
        source_id='mni_pje',
        name='MNI (Modelo Nacional de Interoperabilidade) - PJe',
        category='api_institucional',
        scope='nacional_processual',
        url_documentacao='https://docs.pje.jus.br/servicos-auxiliares/servico-mni-client/',
        accepted_inputs=('numero_processo',),
        requires_credentials=True,
        integration_status='requires_institutional_credentials',
        notes='CONFIRMADO: webservice SOAP institucional (entregarManifestacaoProcessual, consultarProcesso, consultarAvisosPendentes, consultarTeorComunicacao) — acesso é por sistema credenciado, não uso avulso.',
    ),
    'sispreq_pdpj': ExternalSource(
        source_id='sispreq_pdpj',
        name='SisPreq/PDPJ-Br',
        category='api_institucional',
        scope='nacional_precatorios',
        url_documentacao='https://docs.pdpj.jus.br/',
        integration_status='requires_institutional_credentials',
        notes='Já mapeado em official_precatorio_sources.py (chave sispreq_pdpj) — referência cruzada, não duplicado aqui.',
    ),
    'codex_cnj': ExternalSource(
        source_id='codex_cnj',
        name='Codex/CNJ',
        category='api_institucional',
        scope='nacional_processual',
        url_documentacao='',
        integration_status='not_researched',
        notes='Não verificado nesta rodada — entrou no escopo por menção externa, não por pesquisa própria. Não presumir capacidades.',
    ),
    'bnmp': ExternalSource(
        source_id='bnmp',
        name='BNMP - Banco Nacional de Mandados de Prisão',
        category='api_institucional',
        scope='nacional_penal',
        url_documentacao='',
        integration_status='not_researched',
        notes='Não verificado nesta rodada. Fora do escopo principal (precatórios/certidões cível), baixa prioridade para o seu caso de uso atual.',
    ),
    'antecedentes_criminais_pf_sinic': ExternalSource(
        source_id='antecedentes_criminais_pf_sinic',
        name='Certidão de Antecedentes Criminais (SINIC/Polícia Federal)',
        category='api_institucional',
        scope='nacional_penal',
        url_documentacao='https://www.gov.br/conecta/catalogo/apis/antecedentes-criminais',
        accepted_inputs=('nome', 'nome_pai_inicial', 'nome_mae_inicial', 'data_nascimento'),
        requires_credentials=True,
        captcha_expected=True,
        integration_status='captcha_detected',
        notes=(
            'CONFIRMADO ao vivo: existe portal público gratuito (servicos.pf.gov.br/epol-sinic-publico/) que '
            'qualquer pessoa pode usar para emitir "nada consta" — mas o fluxo usa reCAPTCHA, então automação '
            'está fora de cogitação pela regra do projeto. Também existe uma API formal no Catálogo Conecta '
            'gov.br, mas o acesso é via convênio de interoperabilidade governo-a-governo, não contratação '
            'comercial simples. Retorna só "nada consta" — não emite "consta" (isso exige confirmação presencial).'
        ),
    ),
    'escavador_api': ExternalSource(
        source_id='escavador_api',
        name='Escavador API',
        category='api_privada_comercial',
        scope='nacional_processual',
        url_documentacao='https://api.escavador.com/',
        requires_contract=True,
        integration_status='not_researched',
        notes='Alternativa comercial à Judit, mencionada no escopo. Capacidades não verificadas nesta rodada — não presumir campos aceitos sem checar a documentação real. Se você contratar, entra no mesmo padrão de conector configurável que Judit/Serpro.',
    ),
    'jusbrasil_api': ExternalSource(
        source_id='jusbrasil_api',
        name='Jusbrasil Soluções API',
        category='api_privada_comercial',
        scope='nacional_processual',
        url_documentacao='https://www.jusbrasil.com.br/',
        requires_contract=True,
        integration_status='not_researched',
        notes='Outra alternativa comercial. Capacidades não verificadas nesta rodada.',
    ),
    'infosimples_apis': ExternalSource(
        source_id='infosimples_apis',
        name='Infosimples - APIs de automação de portais/certidões',
        category='api_privada_comercial',
        scope='nacional_certidoes_e_portais',
        url_documentacao='https://infosimples.com/',
        requires_contract=True,
        integration_status='not_researched',
        notes=(
            'Provedor comercial que já apareceu nesta pesquisa como fonte terceira documentando parâmetros do '
            'TRF1 e de validação de antecedentes criminais. É uma via prática de terceirizar automação de '
            'portais difíceis (certidões de tribunais, TST/CNDT etc.) em vez de construir scraper próprio. '
            'Não contratado nem testado.'
        ),
    ),
}


def external_sources() -> dict[str, dict[str, Any]]:
    sources = {k: v.as_dict() for k, v in EXTERNAL_SOURCE_REGISTRY.items()}
    if 'datajud_cnj' in sources:
        from ..config import datajud_key_source
        sources['datajud_cnj']['chave_em_uso'] = datajud_key_source()  # 'configurado_pelo_usuario' ou 'chave_publica_padrao' — nunca o valor
    return sources


def master_sources_summary() -> dict[str, Any]:
    """Agrega os 3 registries (precatório oficial, certidões, externo/comercial)
    numa visão única — é o que GET /api/sources devolve."""
    precat_summary = official_precatorio_sources_summary()
    cert_sources = certificate_sources()
    ext_sources = external_sources()

    by_category: dict[str, int] = {}
    for src in ext_sources.values():
        by_category[src['category']] = by_category.get(src['category'], 0) + 1

    ready_now = []
    needs_credential_or_contract = []
    needs_browser_automation = []
    for label, registry in [
        ('precatorio_oficial', official_precatorio_sources()),
        ('certidao', cert_sources),
        ('externo_comercial', ext_sources),
    ]:
        for key, src in registry.items():
            status = src.get('integration_status', '')
            entry = {'source': f'{label}:{key}', 'name': src.get('name')}
            if status in {'implemented', 'implemented_partial', 'implemented_configurable'}:
                ready_now.append(entry)
            elif status in {'requires_credentials', 'requires_institutional_credentials', 'requires_api_contratada'} \
                    or src.get('requires_contract') or src.get('requires_credentials') \
                    or src.get('requires_api_contract') or status == 'requer_api_contratada':
                needs_credential_or_contract.append(entry)
            if src.get('captcha_expected') is True or status == 'captcha_detected':
                needs_browser_automation.append(entry)

    return {
        'total_sources': precat_summary['total_sources'] + len(cert_sources) + len(ext_sources),
        'total_precatorio_oficial': precat_summary['total_sources'],
        'total_certidoes': len(cert_sources),
        'total_externo_comercial': len(ext_sources),
        'externo_comercial_por_categoria': by_category,
        'prontos_para_uso_agora': ready_now,
        'dependem_de_credencial_ou_contrato': needs_credential_or_contract,
        'exigem_automacao_de_navegador_ou_tem_captcha': needs_browser_automation,
    }
