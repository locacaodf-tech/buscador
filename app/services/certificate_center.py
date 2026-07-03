from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

import httpx

from ..config import get_settings
from ..utils.cpf import mask_document, only_digits


# ---------------------------------------------------------------------------
# Status de certidão (regra inegociável do produto):
# 'negativa' / 'positiva' / 'positiva_efeito_negativa' SÓ podem existir com
# documento/código de validação real da fonte oficial. Todo o resto é honesto:
# pendente, erro, requer_*, nao_integrado.
# ---------------------------------------------------------------------------
class CertificateStatus:
    NEGATIVA = 'negativa'
    POSITIVA = 'positiva'
    POSITIVA_EFEITO_NEGATIVA = 'positiva_efeito_negativa'
    PENDENTE = 'pendente'
    ERRO = 'erro'
    REQUER_MANUAL = 'requer_manual'
    REQUER_API_CONTRATADA = 'requer_api_contratada'
    REQUER_LOGIN = 'requer_login'
    REQUER_CERTIFICADO_DIGITAL = 'requer_certificado_digital'
    CAPTCHA_DETECTADO = 'captcha_detectado'
    NAO_INTEGRADO = 'nao_integrado'


@dataclass
class CertificateSource:
    source_id: str
    name: str
    orgao: str
    scope: str
    certificate_types: tuple[str, ...]
    source_type: str  # api_contratada, portal_publico, portal_automation_pendente, a_pesquisar
    official_url: str
    requires_api_contract: bool = False
    requires_login: bool = False
    requires_certificate: bool = False
    captcha_expected: bool | None = None  # None = não verificado
    accepted_inputs: tuple[str, ...] = ()
    integration_status: str = 'not_researched'
    notes: str = ''

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# Registry pesquisado em 01/07/2026 (buscas reais; ver notes de cada fonte).
CERTIFICATE_SOURCE_REGISTRY: dict[str, CertificateSource] = {
    'serpro_consulta_cnd': CertificateSource(
        source_id='serpro_consulta_cnd',
        name='Serpro Consulta CND (Receita Federal + PGFN)',
        orgao='Serpro / RFB / PGFN',
        scope='federal_fiscal',
        certificate_types=('fiscal_cnd',),
        source_type='api_contratada',
        official_url='https://loja.serpro.gov.br/consultacnd',
        requires_api_contract=True,
        captcha_expected=False,
        accepted_inputs=('cpf', 'cnpj', 'nirf'),
        integration_status='implemented_configurable',
        notes=(
            'API REST oficial CONFIRMADA (documentação pública do apicenter Serpro): '
            'POST /v1/certidao com {TipoContribuinte, ContribuinteConsulta, CodigoIdentificacao, GerarCertidaoPdf}, '
            'autenticação Bearer via Consumer Key/Secret contratados na Loja Serpro (custo mensal por faixa de volume). '
            'Retorna dados da CND e pode gerar o PDF da certidão. Conector implementado aqui de forma configurável: '
            'funciona quando SERPRO_CND_CONSUMER_KEY/SECRET estiverem no .env; sem elas, responde requer_api_contratada. '
            'Chamada real ainda não testada (exige contrato ativo).'
        ),
    ),
    'receita_pgfn_cnd_portal': CertificateSource(
        source_id='receita_pgfn_cnd_portal',
        name='Receita/PGFN - Emissão pública de CND (portal)',
        orgao='RFB / PGFN',
        scope='federal_fiscal',
        certificate_types=('fiscal_cnd',),
        source_type='portal_automation_pendente',
        official_url='https://www.regularize.pgfn.gov.br/',
        captcha_expected=None,
        accepted_inputs=('cpf', 'cnpj'),
        integration_status='source_mapping_required',
        notes=(
            'Portal público gratuito confirmado (Regularize/PGFN emite certidão conjunta PGFN/RFB para PF, PJ, '
            'imóvel rural e obra). Presença de captcha não verificada nesta rodada — precisa inspecionar o fluxo real '
            'antes de qualquer automação. Alternativa sem incerteza: a API contratada do Serpro (fonte acima).'
        ),
    ),
    'cjf_certidao_unificada': CertificateSource(
        source_id='cjf_certidao_unificada',
        name='CJF - Certidão Unificada da Justiça Federal',
        orgao='CJF / TRF1-TRF6',
        scope='justica_federal',
        certificate_types=('civel', 'criminal', 'eleitoral'),
        source_type='portal_automation_pendente',
        official_url='https://certidao-unificada.cjf.jus.br/',
        captcha_expected=None,
        accepted_inputs=('cpf', 'cnpj', 'nome'),
        integration_status='source_mapping_required',
        notes=(
            'CONFIRMADO ao vivo: sistema oficial que emite certidão cível/criminal/eleitoral de TODOS os TRFs de uma '
            'vez, eletronicamente, hospedado no portal do CJF — não precisa ir tribunal por tribunal na Justiça Federal. '
            'Emissão por TRF individual também existe (ex.: sistemas.trf1.jus.br/certidao). Fluxo do formulário '
            '(campos exatos, captcha) não verificado ainda — mapear antes de automatizar.'
        ),
    ),
    # Substituído o placeholder único 'tj_certidoes_base' por 27 entradas reais
    # (uma por TJ estadual), pesquisadas em 02/07/2026 — ver
    # docs/CERTIDOES_TJ_ESTADUAIS.md para o levantamento completo com fontes.
    # URLs confirmadas via documento oficial da ANTT (usado para habilitação de
    # motorista, lista os 27 links). Campos exatos e gratuidade só confirmados
    # onde marcado 'source_mapping_required' com notes detalhadas — o resto é
    # 'not_researched' de propósito (só a URL é real, capacidades não verificadas).
    'tjdft_certidoes': CertificateSource(
        source_id='tjdft_certidoes', name='TJDFT - Certidão Judicial de Distribuição (Nada Consta)', orgao='TJDFT', scope='distrital',
        certificate_types=('civel', 'criminal', 'especial', 'falencia_recuperacao'), source_type='portal_html_a_mapear',
        official_url='https://cnc.tjdft.jus.br/solicitacao-externa', requires_login=False,
        accepted_inputs=('nome', 'cpf_cnpj', 'nome_mae'),
        integration_status='source_mapping_required',
        notes=(
            'CONFIRMADO ao vivo: gratuito e instantâneo desde 2014 (extinguiu o cartório pago Rui Barbosa). '
            'Sistema CNC (Certidão Nada Consta), cnc.tjdft.jus.br. 4 tipos: Cível, Criminal, Especial (cível+criminal), '
            'Falência e Recuperação Judicial. CAMPOS DIFEREM POR TIPO: Cível/Falência exige CPF (PF) ou CNPJ (PJ) + '
            'nome; Criminal/Especial exige CPF + nome + NOME DA MÃE (PF) ou CNPJ (PJ). Em caso de homonímia não emite '
            'automático — cai para atendimento via NUCER (inclusive por Microsoft Teams, "Balcão Virtual"). '
            'Validade 30 dias. Captcha não verificado — melhor candidato a pesquisar em seguida, dado o seu foco em DF.'
        ),
    ),
    'tjac_certidoes': CertificateSource(
        source_id='tjac_certidoes', name='TJAC - Certidões cível/criminal', orgao='TJAC', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_a_mapear',
        official_url='https://esaj.tjac.jus.br/sco/abrirCadastro.do', integration_status='not_researched',
        notes='URL confirmada (mesma plataforma SAJ de SP/BA). Campos e captcha não verificados individualmente.',
    ),
    'tjal_certidoes': CertificateSource(
        source_id='tjal_certidoes', name='TJAL - Certidões cível/criminal', orgao='TJAL', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_a_mapear',
        official_url='https://www2.tjal.jus.br/sco/abrirCadastro.do', integration_status='not_researched',
        notes='URL confirmada (plataforma SAJ). Campos e captcha não verificados individualmente.',
    ),
    'tjap_certidoes': CertificateSource(
        source_id='tjap_certidoes', name='TJAP - Certidões cível/criminal', orgao='TJAP', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_a_mapear',
        official_url='https://tucujuris.tjap.jus.br/tucujuris/pages/certidao-publica/certidaopublica.html',
        integration_status='not_researched', notes='URL confirmada (sistema próprio "Tucujuris"). Não verificado a fundo.',
    ),
    'tjam_certidoes': CertificateSource(
        source_id='tjam_certidoes', name='TJAM - Certidões cível/criminal', orgao='TJAM', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_a_mapear',
        official_url='https://consultasaj.tjam.jus.br/sco/abrirCadastro.do', integration_status='not_researched',
        notes='URL confirmada (plataforma SAJ). Não verificado a fundo.',
    ),
    'tjba_certidoes': CertificateSource(
        source_id='tjba_certidoes', name='TJBA - Certidões cível/criminal', orgao='TJBA', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_bloqueado_robots',
        official_url='https://esaj.tjba.jus.br/sco/abrirCadastro.do', requires_login=False, captcha_expected=None,
        integration_status='source_mapping_required',
        notes=(
            'Gratuito confirmado. CONFIRMADO ao vivo: robots.txt do domínio esaj.tjba.jus.br recusa acesso '
            'automatizado — isso barra automação por si só, independente de captcha. Mesma plataforma SAJ de '
            'AC/AL/AM/MS/RN/SC/SP, então provavelmente o mesmo bloqueio se aplica a todos eles.'
        ),
    ),
    'tjce_certidoes': CertificateSource(
        source_id='tjce_certidoes', name='TJCE - Certidões cível/criminal (SIRECE)', orgao='TJCE', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_a_mapear',
        official_url='https://sirece.tjce.jus.br/sirece-web/nova/solicitacao.jsf', requires_login=False,
        accepted_inputs=('nome', 'cpf_cnpj', 'tipo_pessoa', 'instancia'),
        integration_status='source_mapping_required',
        notes='Gratuito confirmado. Sistema próprio (SIRECE) + app "TJCE Mobile". Campos: tipo de pessoa, instância, natureza (cível/criminal) + dados pessoais. Captcha não verificado.',
    ),
    'tjes_certidoes': CertificateSource(
        source_id='tjes_certidoes', name='TJES - Certidões cível/criminal', orgao='TJES', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_a_mapear',
        official_url='https://sistemas.tjes.jus.br/certidaonegativa/sistemas/certidao/CERTIDAOPESQUISA.cfm',
        integration_status='source_mapping_required',
        notes='Gratuito. Emissão automática se "nada consta"; se houver ocorrência, exige ida à Seção de Protocolo/Distribuição. Campos exatos e captcha não verificados.',
    ),
    'tjgo_certidoes': CertificateSource(
        source_id='tjgo_certidoes', name='TJGO - Certidões cível/criminal (PROJUDI)', orgao='TJGO', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_a_mapear',
        official_url='https://projudi.tjgo.jus.br/CertidaoNegativaPositivaPublica?PaginaAtual=1&TipoArea=2&InteressePessoal=S',
        accepted_inputs=('nome', 'cpf_cnpj', 'tipo_pessoa'),
        integration_status='source_mapping_required',
        notes='Gratuito. PF cível/criminal e PJ em formulários separados, 1º e 2º grau. Só emite automaticamente quando o resultado é NEGATIVO — havendo ocorrência, exige atendimento presencial no fórum.',
    ),
    'tjma_certidoes': CertificateSource(
        source_id='tjma_certidoes', name='TJMA - Certidões cível/criminal', orgao='TJMA', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_a_mapear',
        official_url='http://jurisconsult.tjma.jus.br/#/certidao-generate-state-certificate-form',
        integration_status='not_researched', notes='URL confirmada (sistema próprio "Jurisconsult"). Não verificado a fundo.',
    ),
    'tjmt_certidoes': CertificateSource(
        source_id='tjmt_certidoes', name='TJMT - Certidões cível/criminal', orgao='TJMT', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_a_mapear',
        official_url='https://sec.tjmt.jus.br/emitir-certidao-de-primeiro-grau?opcaoCertidao=1',
        integration_status='not_researched', notes='URL confirmada (sistema próprio "SEC"). Não verificado a fundo.',
    ),
    'tjms_certidoes': CertificateSource(
        source_id='tjms_certidoes', name='TJMS - Certidões cível/criminal', orgao='TJMS', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_bloqueado_robots',
        official_url='https://esaj.tjms.jus.br/sco/abrirCadastro.do', integration_status='source_mapping_required',
        notes='Mesma plataforma SAJ do TJBA — provável mesmo bloqueio de robots.txt (não testado individualmente para MS, inferido pela plataforma comum).',
    ),
    'tjmg_certidoes': CertificateSource(
        source_id='tjmg_certidoes', name='TJMG - Certidões cível/criminal (RUPE)', orgao='TJMG', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_a_mapear',
        official_url='https://www8.tjmg.jus.br/certidaoJudicial/faces/emitirCertidao.xhtml', requires_login=False,
        accepted_inputs=('nome', 'cpf_cnpj'),
        integration_status='source_mapping_required',
        notes=(
            'Gratuito confirmado oficialmente. Campos: nome + dados da pessoa; CPF/CNPJ opcional mas recomendado '
            'para maior precisão. Atenção: vários sites terceiros (não oficiais) aparecem em busca cobrando taxa '
            'por isso — nenhum é do TJMG. Captcha não verificado.'
        ),
    ),
    'tjpa_certidoes': CertificateSource(
        source_id='tjpa_certidoes', name='TJPA - Certidões cível/criminal', orgao='TJPA', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_a_mapear',
        official_url='https://consultas.tjpa.jus.br/certidao/pages/pesquisaGeralCentralCertidao.action',
        integration_status='not_researched', notes='URL confirmada. Não verificado a fundo.',
    ),
    'tjpb_certidoes': CertificateSource(
        source_id='tjpb_certidoes', name='TJPB - Certidões cível/criminal (CERTO)', orgao='TJPB', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_a_mapear',
        official_url='https://app.tjpb.jus.br/certo/paginas/publico/areaPublica.jsf',
        integration_status='not_researched', notes='URL confirmada (sistema próprio "CERTO"). Não verificado a fundo.',
    ),
    'tjpr_certidoes': CertificateSource(
        source_id='tjpr_certidoes', name='TJPR - Certidões cível/criminal', orgao='TJPR', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_a_mapear',
        official_url='https://portal.tjpr.jus.br/portletforms/publico/frm.do?idFormulario=4667',
        accepted_inputs=('nome', 'cpf_cnpj', 'tipo_certidao'),
        integration_status='source_mapping_required',
        notes='Gratuito confirmado — CNJ obrigou até serventias privadas a emitir sem custo (2017/2018). PF: negativa criminal/cível/fins eleitorais/improbidade. PJ: negativa quanto a recurso/ação. Captcha não verificado.',
    ),
    'tjpe_certidoes': CertificateSource(
        source_id='tjpe_certidoes', name='TJPE - Certidões cível/criminal', orgao='TJPE', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_captcha_classico',
        official_url='https://certidoesunificadas.app.tjpe.jus.br/', requires_login=False, captcha_expected=True,
        accepted_inputs=('nome', 'cpf', 'titulo_eleitor', 'data_nascimento', 'nacionalidade', 'endereco'),
        integration_status='source_mapping_required',
        notes=(
            'MELHOR ALVO REAL PARA O captcha_relay.py: confirmado ao vivo que usa captcha clássico de imagem '
            '("Imagem de segurança digitada incorretamente" é a mensagem de erro real do sistema). Gratuito. '
            'Campos: nome completo, documento de identificação, CPF, título de eleitor, data de nascimento, '
            'nacionalidade, endereço residencial (PF) / razão social, CNPJ, inscrição estadual (PJ). '
            'Só emite automaticamente se o resultado for "NADA CONSTA" — havendo ocorrência ou homônimo, cai '
            'para atendimento presencial. Próximo passo real: usar /api/portal-automation/start apontado pra cá.'
        ),
    ),
    'tjpi_certidoes': CertificateSource(
        source_id='tjpi_certidoes', name='TJPI - Certidões cível/criminal (Themis)', orgao='TJPI', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_a_mapear',
        official_url='http://www.tjpi.jus.br/themisconsulta/certidao',
        integration_status='not_researched', notes='URL confirmada (sistema "Themis"). Não verificado a fundo.',
    ),
    'tjrj_certidoes': CertificateSource(
        source_id='tjrj_certidoes', name='TJRJ - Certidões cível/criminal/fazendária (CJE)', orgao='TJRJ', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_a_mapear',
        official_url='https://www4.tjrj.jus.br/portal-extrajudicial/certidao/judicial/solicitar', requires_login=False,
        accepted_inputs=('nome', 'cpf', 'rg', 'data_nascimento', 'nome_pai', 'nome_mae'),
        integration_status='source_mapping_required',
        notes=(
            'Gratuito confirmado (determinação CNJ/STF, Reclamação RGD 0002154-83.2021.2.00.0000). Sistema '
            'Certidão Judicial Eletrônica (CJE). Campos: nome, CPF, RG, data de nascimento, nome dos pais. '
            'Limite de 10 pedidos/dia por CPF/CNPJ. Validade 90 dias. Captcha não verificado. Nota à parte: '
            'documento da ANTT (contexto de habilitação de motorista) diz que a capital do RJ exige presença '
            'em 4 ofícios distribuidores para essa finalidade específica — não é a regra geral.'
        ),
    ),
    'tjrn_certidoes': CertificateSource(
        source_id='tjrn_certidoes', name='TJRN - Certidões cível/criminal', orgao='TJRN', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_bloqueado_robots',
        official_url='https://esaj.tjrn.jus.br/sco/abrirCadastro.do', integration_status='source_mapping_required',
        notes='Mesma plataforma SAJ do TJBA — provável mesmo bloqueio de robots.txt (inferido pela plataforma comum, não testado individualmente).',
    ),
    'tjrs_certidoes': CertificateSource(
        source_id='tjrs_certidoes', name='TJRS - Certidões cível/criminal', orgao='TJRS', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_a_mapear',
        official_url='https://www.tjrs.jus.br/novo/processos-e-servicos/servicos-processuais/emissao-de-antecedentes-e-certidoes/',
        accepted_inputs=('nome', 'cpf_cnpj'),
        integration_status='source_mapping_required',
        notes='Gratuito confirmado. Emissão eletrônica obrigatória na comarca de Porto Alegre. Vários modelos (alvará de folha corrida, cível 1º/2º grau, família, insolvência, falência). Campos exatos e captcha não verificados.',
    ),
    'tjro_certidoes': CertificateSource(
        source_id='tjro_certidoes', name='TJRO - Certidões cível/criminal', orgao='TJRO', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_a_mapear',
        official_url='https://webapp.tjro.jus.br/certidaoonline/pages/cnpg.xhtml',
        integration_status='not_researched', notes='URL confirmada. Não verificado a fundo.',
    ),
    'tjrr_certidoes': CertificateSource(
        source_id='tjrr_certidoes', name='TJRR - Certidões cível/criminal', orgao='TJRR', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_a_mapear',
        official_url='https://www.tjrr.jus.br/index.php/certidao-negativa',
        integration_status='not_researched', notes='URL confirmada. Não verificado a fundo.',
    ),
    'tjsc_certidoes': CertificateSource(
        source_id='tjsc_certidoes', name='TJSC - Certidões cível/criminal', orgao='TJSC', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_gov_br',
        official_url='https://certidoes.tjsc.jus.br/', requires_login=True,
        accepted_inputs=('nome', 'cpf', 'rg', 'orgao_expedidor', 'nome_mae', 'nome_pai', 'data_nascimento', 'email', 'telefone', 'finalidade'),
        integration_status='source_mapping_required',
        notes=(
            'Gratuito confirmado. Sistema novo EXIGE conta gov.br nível prata ou ouro — não é login simples, é '
            'identidade verificada pessoal, o que impede automação responsável. Sistema antigo (esaj.tjsc.jus.br) '
            'usa a mesma plataforma SAJ bloqueada por robots.txt no TJBA. Campos do formulário: nome, CPF, RG, '
            'órgão expedidor, nome da mãe, nome do pai, data de nascimento, e-mail, telefone, finalidade.'
        ),
    ),
    'tjsp_certidoes': CertificateSource(
        source_id='tjsp_certidoes', name='TJSP - Certidões cível/criminal', orgao='TJSP', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_a_mapear',
        official_url='https://www.tjsp.jus.br/Certidoes/Certidoes/CertidoesPrimeiraInstancia', requires_login=False,
        accepted_inputs=('nome', 'rg', 'cpf_cnpj', 'nome_pai', 'nome_mae', 'data_nascimento', 'naturalidade', 'email'),
        integration_status='source_mapping_required',
        notes=(
            'Link corrigido em 03/07/2026: apontava por engano pra página de Perguntas Frequentes, não pro '
            'cadastro de pedido — corrigido pra "CertidoesPrimeiraInstancia", que tem o botão "Cadastro de Pedido '
            'de Certidão" levando direto ao formulário eletrônico. Gratuito confirmado (1ª instância, capital e '
            'interior). Campos: nome completo, RG, CPF/CNPJ, nome completo do pai e da mãe, data de nascimento, '
            'naturalidade, e-mail. Certidão criminal só para nascidos a partir de 1969 (mais antigos exigem '
            'presença). O sistema de 2ª instância (certidoes.tjsp.jus.br) é separado e EXIGE conta gov.br nível '
            'prata/ouro — não é o link usado aqui. Emissão real usa a plataforma SAJ (esaj.tjsp.jus.br), a mesma '
            'bloqueada por robots.txt no TJBA — automação não é opção, só preenchimento manual mesmo.'
        ),
    ),
    'tjse_certidoes': CertificateSource(
        source_id='tjse_certidoes', name='TJSE - Certidões cível/criminal', orgao='TJSE', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_a_mapear',
        official_url='https://www.tjse.jus.br/portal/servicos/judiciais/certidao-online/solicitacao-de-certidao-negativa',
        integration_status='not_researched', notes='URL confirmada. Não verificado a fundo.',
    ),
    'tjto_certidoes': CertificateSource(
        source_id='tjto_certidoes', name='TJTO - Certidões cível/criminal (eproc)', orgao='TJTO', scope='justica_estadual',
        certificate_types=('civel', 'criminal'), source_type='portal_html_a_mapear',
        official_url='https://eproc1.tjto.jus.br/eprocV2_prod_1grau/externo_controlador.php?acao=cj_online',
        integration_status='not_researched', notes='URL confirmada (sistema eproc). Não verificado a fundo.',
    ),
    'stf_certidoes': CertificateSource(
        source_id='stf_certidoes', name='STF - Certidões', orgao='STF', scope='tribunal_superior',
        certificate_types=('civel', 'criminal'), source_type='a_pesquisar',
        official_url='https://portal.stf.jus.br/', integration_status='not_researched',
        accepted_inputs=(), notes='Não pesquisado nesta rodada.',
    ),
    'stj_certidoes': CertificateSource(
        source_id='stj_certidoes', name='STJ - Certidões', orgao='STJ', scope='tribunal_superior',
        certificate_types=('civel', 'criminal'), source_type='a_pesquisar',
        official_url='https://www.stj.jus.br/', integration_status='not_researched',
        accepted_inputs=(), notes='Não pesquisado nesta rodada.',
    ),
    'tst_certidoes': CertificateSource(
        source_id='tst_certidoes', name='TST - Certidões (inclui CNDT)', orgao='TST', scope='tribunal_superior',
        certificate_types=('trabalhista_cndt',), source_type='a_pesquisar',
        official_url='https://www.tst.jus.br/certidao1', integration_status='not_researched',
        accepted_inputs=('cpf', 'cnpj'),
        notes='CNDT (Certidão Negativa de Débitos Trabalhistas) é emitida pelo TST — candidata forte a próxima pesquisa, muito usada em due diligence. Não pesquisado/verificado nesta rodada.',
    ),
    'trt_certidoes_base': CertificateSource(
        source_id='trt_certidoes_base', name='TRTs - Certidões trabalhistas (base genérica)', orgao='TRT1-24',
        scope='justica_trabalhista', certificate_types=('civel', 'criminal', 'trabalhista'),
        source_type='a_pesquisar', official_url='https://www.csjt.jus.br/',
        integration_status='not_researched', accepted_inputs=(),
        notes='Cada TRT tem portal próprio. Não pesquisado nesta rodada.',
    ),
}


def certificate_sources() -> dict[str, dict[str, Any]]:
    return {k: v.as_dict() for k, v in CERTIFICATE_SOURCE_REGISTRY.items()}


def build_certificate_plan(document: str | None, certificate_types: list[str] | None = None) -> dict[str, Any]:
    """Monta o plano de emissão por camadas para um documento, sem executar nada."""
    wanted = set(certificate_types or [])
    steps = []
    for source in CERTIFICATE_SOURCE_REGISTRY.values():
        if wanted and not (wanted & set(source.certificate_types)):
            continue
        steps.append({
            'source_id': source.source_id,
            'name': source.name,
            'certificate_types': list(source.certificate_types),
            'integration_status': source.integration_status,
            'ready_to_execute': source.integration_status == 'implemented_configurable',
            'blockers': [b for b in [
                'requer contrato de API (Serpro)' if source.requires_api_contract else None,
                'requer login' if source.requires_login else None,
                'requer certificado digital' if source.requires_certificate else None,
                'captcha não verificado' if source.captcha_expected is None and source.source_type != 'api_contratada' else None,
                'fonte ainda não pesquisada' if source.integration_status == 'not_researched' else None,
            ] if b],
        })
    return {
        'document_masked': mask_document(document) if document else None,
        'steps': steps,
        'note': 'Plano informativo. Nenhuma certidão é emitida por este endpoint — use POST /api/certificates/request por fonte.',
    }


# ---------------------------------------------------------------------------
# Conector Serpro Consulta CND (configurável). Endpoint e payload copiados da
# documentação oficial pública (apicenter.estaleiro.serpro.gov.br). A chamada
# real exige contrato ativo — sem as credenciais no .env, resposta honesta.
# ---------------------------------------------------------------------------
SERPRO_TOKEN_URL = 'https://gateway.apiserpro.serpro.gov.br/token'
SERPRO_CND_URL = 'https://gateway.apiserpro.serpro.gov.br/consulta-cnd/v1/certidao'


def serpro_tipo_contribuinte(document: str) -> int | None:
    digits = only_digits(document)
    if len(digits) == 11:
        return 2  # Pessoa Física (conforme convenção da doc; validar no contrato)
    if len(digits) == 14:
        return 1  # Pessoa Jurídica
    return None


async def request_serpro_cnd(document: str, gerar_pdf: bool = True) -> dict[str, Any]:
    settings = get_settings()
    consumer_key = getattr(settings, 'serpro_cnd_consumer_key', '') or ''
    consumer_secret = getattr(settings, 'serpro_cnd_consumer_secret', '') or ''
    consulted_at = datetime.now(timezone.utc).isoformat()

    if not consumer_key or not consumer_secret:
        return {
            'status': CertificateStatus.REQUER_API_CONTRATADA,
            'message': (
                'API Serpro Consulta CND não configurada. É uma API oficial paga (Loja Serpro, custo mensal por faixa '
                'de consumo). Após contratar, coloque SERPRO_CND_CONSUMER_KEY e SERPRO_CND_CONSUMER_SECRET no .env — '
                'nada muda no código. Enquanto isso, a CND pode ser emitida manualmente e grátis no portal '
                'https://www.regularize.pgfn.gov.br/.'
            ),
            'fonte_url': 'https://loja.serpro.gov.br/consultacnd',
            'consulted_at': consulted_at,
        }

    tipo = serpro_tipo_contribuinte(document)
    if tipo is None:
        return {
            'status': CertificateStatus.ERRO,
            'message': f'Documento inválido para CND: precisa ser CPF (11 dígitos) ou CNPJ (14). Recebi {len(only_digits(document))} dígitos.',
            'consulted_at': consulted_at,
        }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            token_resp = await client.post(
                SERPRO_TOKEN_URL,
                data={'grant_type': 'client_credentials'},
                auth=(consumer_key, consumer_secret),
            )
            if token_resp.status_code >= 400:
                return {'status': CertificateStatus.ERRO,
                        'message': f'Falha na autenticação Serpro (HTTP {token_resp.status_code}). Confira as credenciais contratadas.',
                        'consulted_at': consulted_at}
            access_token = token_resp.json().get('access_token')
            cnd_resp = await client.post(
                SERPRO_CND_URL,
                headers={'Authorization': f'Bearer {access_token}', 'Accept': 'application/json'},
                json={
                    'TipoContribuinte': tipo,
                    'ContribuinteConsulta': only_digits(document),
                    'CodigoIdentificacao': getattr(settings, 'serpro_cnd_codigo_identificacao', '') or '9001',
                    'GerarCertidaoPdf': gerar_pdf,
                },
            )
            raw = cnd_resp.json() if 'json' in (cnd_resp.headers.get('content-type') or '') else {'texto': cnd_resp.text[:2000]}
            if cnd_resp.status_code >= 400:
                return {'status': CertificateStatus.ERRO,
                        'message': f'Serpro CND retornou HTTP {cnd_resp.status_code}.',
                        'raw': raw, 'consulted_at': consulted_at, 'fonte_url': SERPRO_CND_URL}
            # Interpretação do status da certidão fica PENDENTE de validação com contrato
            # real: a doc pública mostra "Status 7 = em processamento", mas o mapa completo
            # (negativa/positiva/etc) não está confirmado. Não inventar: devolver raw + pendente.
            return {
                'status': CertificateStatus.PENDENTE,
                'message': (
                    'Consulta enviada ao Serpro com sucesso. O mapeamento do código de status da certidão para '
                    'negativa/positiva ainda precisa ser validado com um retorno real do contrato — o dado bruto '
                    'está em raw para conferência manual até lá.'
                ),
                'raw': raw,
                'consulted_at': consulted_at,
                'fonte_url': SERPRO_CND_URL,
            }
    except Exception as exc:
        return {'status': CertificateStatus.ERRO, 'message': f'Falha ao consultar Serpro CND: {exc}', 'consulted_at': consulted_at}


async def request_certificate(source_id: str, certificate_type: str, document: str | None, name: str | None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Executa (ou explica por que não pode executar) um pedido de certidão."""
    source = CERTIFICATE_SOURCE_REGISTRY.get(source_id)
    consulted_at = datetime.now(timezone.utc).isoformat()
    if not source:
        return {'status': CertificateStatus.ERRO,
                'message': f'Fonte de certidão desconhecida: {source_id}. Disponíveis: {", ".join(sorted(CERTIFICATE_SOURCE_REGISTRY))}.',
                'consulted_at': consulted_at}

    if certificate_type not in source.certificate_types:
        return {'status': CertificateStatus.ERRO,
                'message': f'{source.name} não emite certidão do tipo "{certificate_type}". Tipos: {", ".join(source.certificate_types)}.',
                'fonte_url': source.official_url, 'consulted_at': consulted_at}

    if source_id == 'serpro_consulta_cnd':
        if not document:
            return {'status': CertificateStatus.ERRO, 'message': 'CND exige CPF ou CNPJ.', 'consulted_at': consulted_at}
        return await request_serpro_cnd(document)

    # Fontes mapeadas/não pesquisadas: resposta honesta, nunca certidão inventada.
    if source.integration_status == 'not_researched':
        return {'status': CertificateStatus.NAO_INTEGRADO,
                'message': f'{source.name}: fonte registrada no escopo mas ainda não pesquisada — capacidades, captcha e fluxo desconhecidos. Emita manualmente em {source.official_url} por enquanto.',
                'fonte_url': source.official_url, 'consulted_at': consulted_at}
    return {'status': CertificateStatus.NAO_INTEGRADO,
            'message': f'{source.name}: fonte mapeada, mas ainda não integrada ({source.notes[:180]}...). Emita manualmente em {source.official_url} por enquanto.',
            'fonte_url': source.official_url, 'consulted_at': consulted_at}
