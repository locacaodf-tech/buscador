"""IntakeBot manual (v31): transforma texto solto de WhatsApp em caso
estruturado — extrai CPF/CNPJ, CNJ (com ou sem pontuação, mesmo com
separadores não-padrão como ponto em vez de hífen), infere tribunal
provável a partir dos próprios dígitos do CNJ, identifica cidade/UF citada,
ente devedor mencionado, e aponta divergência quando o que a pessoa
escreveu não bate com o que os dígitos do CNJ realmente indicam.

Escopo deliberadamente manual (decisão do usuário): sem OCR, sem API paga
de visão, sem WhatsApp Business ativado. Extração por regex/heurística
sobre texto que o próprio usuário colou — nada de IA generativa nem
serviço externo novo."""
from __future__ import annotations

import re
from typing import Any

from ..utils.cnj import normalize_cnj, format_cnj, infer_tribunal_from_cnj, split_cnj_suffix
from ..utils.cpf import only_digits, mask_document

# ---------------------------------------------------------------------------
# Tabelas de jurisdição — fonte: Portal CNJ (cnj.jus.br/poder-judiciario/
# tribunais/), confirmado em 2026-07-06. Usadas só pra checar divergência
# entre o que a pessoa disse e o que o número realmente indica — nunca pra
# inventar tribunal quando os dígitos já não permitem inferir (essa parte
# já existe em infer_tribunal_from_cnj).
# ---------------------------------------------------------------------------

TRF_PARA_UFS = {
    'TRF1': {'AC', 'AM', 'AP', 'BA', 'DF', 'GO', 'MA', 'MT', 'PA', 'PI', 'RO', 'RR', 'TO'},
    'TRF2': {'ES', 'RJ'},
    'TRF3': {'MS', 'SP'},
    'TRF4': {'PR', 'RS', 'SC'},
    'TRF5': {'AL', 'CE', 'PB', 'PE', 'RN', 'SE'},
    'TRF6': {'MG'},
}

TRT_PARA_UFS = {
    'TRT1': {'RJ'}, 'TRT2': {'SP'}, 'TRT3': {'MG'}, 'TRT4': {'RS'}, 'TRT5': {'BA'},
    'TRT6': {'PE'}, 'TRT7': {'CE'}, 'TRT8': {'PA', 'AP'}, 'TRT9': {'PR'}, 'TRT10': {'DF', 'TO'},
    'TRT11': {'AM', 'RR'}, 'TRT12': {'SC'}, 'TRT13': {'PB'}, 'TRT14': {'AC', 'RO'}, 'TRT15': {'SP'},
    'TRT16': {'MA'}, 'TRT17': {'ES'}, 'TRT18': {'GO'}, 'TRT19': {'AL'}, 'TRT20': {'SE'},
    'TRT21': {'RN'}, 'TRT22': {'PI'}, 'TRT23': {'MT'}, 'TRT24': {'MS'},
}

TJ_PARA_UF = {
    'TJAC': {'AC'}, 'TJAL': {'AL'}, 'TJAP': {'AP'}, 'TJAM': {'AM'}, 'TJBA': {'BA'},
    'TJCE': {'CE'}, 'TJDFT': {'DF'}, 'TJES': {'ES'}, 'TJGO': {'GO'}, 'TJMA': {'MA'},
    'TJMT': {'MT'}, 'TJMS': {'MS'}, 'TJMG': {'MG'}, 'TJPA': {'PA'}, 'TJPB': {'PB'},
    'TJPR': {'PR'}, 'TJPE': {'PE'}, 'TJPI': {'PI'}, 'TJRJ': {'RJ'}, 'TJRN': {'RN'},
    'TJRS': {'RS'}, 'TJRO': {'RO'}, 'TJRR': {'RR'}, 'TJSC': {'SC'}, 'TJSP': {'SP'},
    'TJSE': {'SE'}, 'TJTO': {'TO'},
}

# Segmento (dígito J do CNJ) -> nome humano + prefixo de tribunal + mapa de UF
SEGMENTO_INFO = {
    '1': {'nome': 'Supremo Tribunal Federal', 'prefixo': None},
    '2': {'nome': 'Conselho Nacional de Justiça', 'prefixo': None},
    '3': {'nome': 'Superior Tribunal de Justiça', 'prefixo': None},
    '4': {'nome': 'Justiça Federal', 'prefixo': 'TRF', 'ufs': TRF_PARA_UFS},
    '5': {'nome': 'Justiça do Trabalho', 'prefixo': 'TRT', 'ufs': TRT_PARA_UFS},
    '6': {'nome': 'Justiça Eleitoral', 'prefixo': 'TRE'},
    '7': {'nome': 'Justiça Militar da União', 'prefixo': None},
    '8': {'nome': 'Justiça Estadual', 'prefixo': 'TJ', 'ufs': TJ_PARA_UF},
    '9': {'nome': 'Justiça Militar Estadual', 'prefixo': None},
}

# UF -> nomes de capital/cidades grandes reconhecidas (lista deliberadamente
# não-exaustiva: cobre capitais + praças forenses grandes o suficiente pra
# aparecer com frequência em mensagem de cliente; cidades menores não
# reconhecidas ficam só como "não identificado", nunca um palpite errado).
CIDADE_PARA_UF = {
    'rio branco': 'AC', 'maceio': 'AL', 'macapa': 'AP', 'manaus': 'AM',
    'salvador': 'BA', 'fortaleza': 'CE', 'brasilia': 'DF', 'vitoria': 'ES',
    'goiania': 'GO', 'sao luis': 'MA', 'cuiaba': 'MT', 'campo grande': 'MS',
    'belo horizonte': 'MG', 'belem': 'PA', 'joao pessoa': 'PB', 'curitiba': 'PR',
    'recife': 'PE', 'teresina': 'PI', 'rio de janeiro': 'RJ', 'natal': 'RN',
    'porto alegre': 'RS', 'porto velho': 'RO', 'boa vista': 'RR', 'florianopolis': 'SC',
    'sao paulo': 'SP', 'aracaju': 'SE', 'palmas': 'TO',
    # cidades grandes não-capitais que aparecem com frequência real
    'juazeiro do norte': 'CE', 'campinas': 'SP', 'santos': 'SP', 'guarulhos': 'SP',
    'caucaia': 'CE', 'sobral': 'CE',
}

UF_VALIDAS = {
    'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS',
    'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC',
    'SP', 'SE', 'TO',
}

# Nome do ESTADO por extenso -> sigla (achado real: mensagem de cliente às
# vezes cita o estado direto, tipo "no Pará?", não uma cidade nem a sigla
# de 2 letras isolada).
NOME_ESTADO_PARA_UF = {
    'acre': 'AC', 'alagoas': 'AL', 'amapa': 'AP', 'amazonas': 'AM', 'bahia': 'BA',
    'ceara': 'CE', 'distrito federal': 'DF', 'espirito santo': 'ES', 'goias': 'GO',
    'maranhao': 'MA', 'mato grosso do sul': 'MS', 'mato grosso': 'MT', 'minas gerais': 'MG',
    'para': 'PA', 'paraiba': 'PB', 'parana': 'PR', 'pernambuco': 'PE', 'piaui': 'PI',
    'rio de janeiro': 'RJ', 'rio grande do norte': 'RN', 'rio grande do sul': 'RS',
    'rondonia': 'RO', 'roraima': 'RR', 'santa catarina': 'SC', 'sao paulo': 'SP',
    'sergipe': 'SE', 'tocantins': 'TO',
}

ENTES_DEVEDORES_CONHECIDOS = [
    'INSS', 'União', 'Fazenda Nacional', 'Fazenda Pública', 'Estado', 'Município',
    'Prefeitura', 'Governo do Estado', 'Governo Federal',
]


def _remover_acentos(texto: str) -> str:
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')


def extrair_cnj_candidatos(texto: str) -> list[dict[str, Any]]:
    """Acha número CNJ dentro de texto livre, mesmo mal formatado (com
    ponto em vez de hífen, sem nenhuma pontuação, ou com sufixo/incidente
    tipo '/01' no final — achado real: um CNJ com sufixo colado batia 22
    dígitos, não 20, e ficava invisível pro reconhecedor). Devolve lista
    de dicts com 'cnj' (só os 20 dígitos) e 'sufixo' (ou None)."""
    from ..utils.cnj import split_cnj_suffix
    candidatos = []
    vistos = set()
    for match in re.finditer(r'[\d][\d.\-/\s]{18,34}[\d]', texto):
        base, sufixo = split_cnj_suffix(match.group(0))
        digitos = only_digits(base)
        if len(digitos) == 20 and digitos not in vistos:
            vistos.add(digitos)
            candidatos.append({'cnj': digitos, 'sufixo': sufixo})
    return candidatos


def extrair_cpf(texto: str) -> str | None:
    for match in re.finditer(r'\d{3}\.?\d{3}\.?\d{3}-?\d{2}', texto):
        digitos = only_digits(match.group(0))
        if len(digitos) == 11:
            return digitos
    return None


def extrair_cnpj(texto: str) -> str | None:
    for match in re.finditer(r'\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}', texto):
        digitos = only_digits(match.group(0))
        if len(digitos) == 14:
            return digitos
    return None


def extrair_nome(texto: str) -> str | None:
    """Heurística simples: texto que aparece logo depois da palavra 'nome'
    (com ou sem dois-pontos), até o próximo ponto final ou fim da linha."""
    match = re.search(r'\bnome\b[:\s]+([A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+){0,4})', texto, re.IGNORECASE)
    if match:
        return match.group(1).strip().rstrip('.')
    return None


def extrair_cidade_uf(texto: str) -> dict[str, str | None]:
    """Procura UF citada diretamente (sigla de 2 letras isolada, tipo '/CE'
    ou 'CE)'), nome de estado por extenso (tipo 'Pará', 'Ceará') ou nome de
    cidade reconhecida. Nunca inventa — se não achar nada reconhecível,
    devolve None nos dois campos."""
    texto_norm = _remover_acentos(texto.lower())

    cidade_achada = None
    uf_por_cidade = None
    for cidade, uf in CIDADE_PARA_UF.items():
        if cidade in texto_norm:
            cidade_achada = cidade.title()
            uf_por_cidade = uf
            break

    # Nomes de estado mais longos primeiro (ex.: "mato grosso do sul" antes
    # de "mato grosso"), senão o substring mais curto sempre ganha errado.
    uf_por_nome_estado = None
    for nome_estado in sorted(NOME_ESTADO_PARA_UF, key=len, reverse=True):
        if re.search(r'\b' + re.escape(nome_estado) + r'\b', texto_norm):
            uf_por_nome_estado = NOME_ESTADO_PARA_UF[nome_estado]
            break

    uf_direta = None
    for match in re.finditer(r'\b([A-Z]{2})\b', texto):
        if match.group(1) in UF_VALIDAS:
            uf_direta = match.group(1)
            break

    return {'cidade': cidade_achada, 'uf': uf_direta or uf_por_cidade or uf_por_nome_estado}


def extrair_ente_devedor(texto: str) -> str | None:
    for ente in ENTES_DEVEDORES_CONHECIDOS:
        if re.search(r'\b' + re.escape(ente) + r'\b', texto, re.IGNORECASE):
            return ente
    return None


def analisar_cnj(cnj_normalizado: str) -> dict[str, Any]:
    """Devolve segmento, tribunal provável, UFs que esse tribunal cobre e a
    fonte de consulta recomendada — a base pra detectar divergência com o
    que a pessoa disse no texto e pra saber se já existe consulta
    automática pra esse tribunal específico (checando o registry real do
    DataJud, que cobre nacionalmente: 6 TRFs, 27 TJs, 24 TRTs, TREs — não
    um palpite, é o mesmo registry que o DataJudBot usa de verdade)."""
    from ..connectors.tribunal_registry import TRIBUNAL_ALIASES

    n = normalize_cnj(cnj_normalizado)
    if len(n) != 20:
        return {'segmento_codigo': None, 'segmento_nome': None, 'tribunal_provavel': None, 'ufs_cobertas': None, 'fonte_recomendada': None}
    segmento_codigo = n[13]
    info_segmento = SEGMENTO_INFO.get(segmento_codigo, {})
    tribunal = infer_tribunal_from_cnj(n)
    ufs_cobertas = None
    if tribunal and info_segmento.get('ufs'):
        ufs_cobertas = info_segmento['ufs'].get(tribunal)

    if tribunal and tribunal in TRIBUNAL_ALIASES:
        fonte_recomendada = f'Consulta automática disponível via DataJud ({tribunal}).'
    elif tribunal:
        fonte_recomendada = f'Tribunal provável identificado ({tribunal}). Consulta automática ainda não implementada para este tribunal. Fonte manual recomendada: portal oficial correspondente.'
    else:
        nome_segmento = info_segmento.get('nome') or 'segmento não identificado'
        fonte_recomendada = f'Não foi possível inferir o tribunal específico a partir deste CNJ ({nome_segmento}). Consulte a fonte oficial correspondente a esse segmento.'

    return {
        'segmento_codigo': segmento_codigo,
        'segmento_nome': info_segmento.get('nome'),
        'tribunal_provavel': tribunal,
        'ufs_cobertas': sorted(ufs_cobertas) if ufs_cobertas else None,
        'fonte_recomendada': fonte_recomendada,
    }


def mascarar_documentos_no_texto(texto: str) -> str:
    """Substitui qualquer CPF/CNPJ encontrado dentro de um texto livre pela
    versão mascarada — usado pra nunca devolver o texto_original com
    documento em claro na resposta da API (achado real: eu excluía as
    chaves 'cpf'/'cnpj' da resposta, mas o texto_original ecoado ainda
    trazia o número completo do jeito que a pessoa digitou).

    Protege primeiro os trechos que já são CNJ (achado real de auditoria:
    um CNJ de 20 dígitos contém, por coincidência, uma sequência de 11
    dígitos que a regex solta de CPF capturava e mascarava, corrompendo o
    próprio número do processo na tela — ex.: "00007659720235070016"
    virava "000076597202.***.***-16"). A mesma proteção que já existia na
    extração de CPF/CNPJ (processar_mensagem) precisa valer aqui também,
    já que são dois pontos de código diferentes sobre o mesmo texto."""
    cnj_candidatos = extrair_cnj_candidatos(texto)

    # Substitui cada CNJ encontrado por um marcador temporário único,
    # protegendo-o de qualquer regex de CPF/CNPJ que rode depois — e
    # devolve ao final, intacto, no lugar exato de onde saiu.
    protegido = texto
    marcadores: dict[str, str] = {}
    for i, candidato in enumerate(cnj_candidatos):
        marcador = f'\x00CNJ{i}\x00'
        # acha o trecho exato (com pontuação e sufixo originais, se houver) que gerou esse CNJ
        for match in re.finditer(r'[\d][\d.\-/\s]{18,34}[\d]', protegido):
            base, _ = split_cnj_suffix(match.group(0))
            if only_digits(base) == candidato['cnj'] and match.group(0) not in marcadores.values():
                marcadores[marcador] = match.group(0)
                protegido = protegido.replace(match.group(0), marcador, 1)
                break

    resultado = protegido
    for match in re.finditer(r'\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)', resultado):
        digitos = only_digits(match.group(0))
        if len(digitos) == 11:
            resultado = resultado.replace(match.group(0), mask_document(digitos))
    for match in re.finditer(r'\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}', resultado):
        digitos = only_digits(match.group(0))
        if len(digitos) == 14:
            resultado = resultado.replace(match.group(0), mask_document(digitos))

    for marcador, original in marcadores.items():
        resultado = resultado.replace(marcador, original)
    return resultado


# ---------------------------------------------------------------------------
# v31e/v31f: classe do documento, processo referência, requisitório/
# precatório, e sinalizadores processuais bem delimitados (presença de
# frase específica) — não tentei extrair "advogados" por nome livre, já
# que isso é bem mais arriscado de acertar por regex do que os campos
# abaixo (todos têm um marcador textual claro: uma palavra-chave, um
# rótulo antes do valor, ou uma frase fixa).
# ---------------------------------------------------------------------------

CLASSES_DOCUMENTO_CONHECIDAS = [
    ('ação rescisória', 'Ação Rescisória'),
    ('acao rescisoria', 'Ação Rescisória'),
    ('cumprimento de sentença', 'Cumprimento de Sentença'),
    ('cumprimento de sentenca', 'Cumprimento de Sentença'),
    ('ofício requisitório', 'Ofício Requisitório'),
    ('oficio requisitorio', 'Ofício Requisitório'),
    ('precatório', 'Precatório'),
    ('precatorio', 'Precatório'),
    ('rpv', 'RPV'),
    ('requisição de pequeno valor', 'RPV'),
    ('incidente', 'Incidente'),
    ('agravo', 'Agravo'),
    ('recurso especial', 'Recurso Especial'),
    ('recurso extraordinário', 'Recurso Extraordinário'),
    ('recurso', 'Recurso'),
    ('execução', 'Execução'),
    ('execucao', 'Execução'),
]

PALAVRAS_CHAVE_REQUISITORIO_PRECATORIO = [
    'ofício requisitório', 'oficio requisitorio', 'precatório', 'precatorio', 'rpv', 'depre',
    'fazenda pública', 'fazenda publica', 'valor global da requisição', 'valor global da requisicao',
    'natureza do crédito', 'natureza do credito', 'trânsito em julgado', 'transito em julgado',
]


def detectar_classe_documento(texto: str) -> str | None:
    """Detecta o tipo/classe do documento por palavra-chave — sempre a
    PRIMEIRA classe encontrada na ordem da lista (mais específica primeiro:
    'ação rescisória' antes de 'recurso' genérico, por exemplo)."""
    texto_norm = _remover_acentos(texto.lower())
    for chave, rotulo in CLASSES_DOCUMENTO_CONHECIDAS:
        if _remover_acentos(chave) in texto_norm:
            return rotulo
    return None


def eh_documento_requisitorio_ou_precatorio(texto: str) -> bool:
    """True se o texto tiver pelo menos uma das palavras-chave que
    normalmente aparecem em ofício requisitório / precatório / RPV —
    usado pra saber se, mesmo sem retorno no DataJud, a próxima ação deve
    apontar pro órgão de precatórios do tribunal, não um erro genérico."""
    texto_norm = _remover_acentos(texto.lower())
    return any(_remover_acentos(chave) in texto_norm for chave in PALAVRAS_CHAVE_REQUISITORIO_PRECATORIO)


def extrair_processo_referencia(texto: str) -> dict[str, Any] | None:
    """Acha 'processo referência: NNNNNNN...' (ou 'processo de referência')
    e devolve o CNJ (base + sufixo, igual ao processo principal). Sem
    isso, um documento de ação rescisória ou incidente que cita o
    processo original perdia essa informação por completo."""
    match = re.search(
        r'processo\s+(?:de\s+)?refer[êe]ncia\s*[:\s]+([\d][\d.\-/\s]{18,34}[\d])',
        texto, re.IGNORECASE,
    )
    if not match:
        return None
    base, sufixo = split_cnj_suffix(match.group(1))
    digitos = only_digits(base)
    if len(digitos) != 20:
        return None
    return {'cnj': digitos, 'sufixo': sufixo}


def extrair_valor_causa(texto: str) -> str | None:
    """Acha 'valor da causa: R$ X' ou 'valor global da requisição: R$ X' —
    reaproveita o mesmo padrão de valor monetário em reais, só muda o
    rótulo procurado antes do valor."""
    match = re.search(
        r'valor\s+(?:da\s+causa|global\s+da\s+requisi[çc][ãa]o)\s*[:\s]+R?\$?\s*([\d.,]+)',
        texto, re.IGNORECASE,
    )
    return match.group(1).strip() if match else None


def extrair_orgao_julgador(texto: str) -> str | None:
    """Heurística simples: texto que aparece logo depois de 'órgão
    julgador' (com ou sem dois-pontos), até o próximo ponto final ou fim
    da linha."""
    match = re.search(r'[óo]rg[ãa]o\s+julgador\s*[:\s]+([^\n.]{3,80})', texto, re.IGNORECASE)
    return match.group(1).strip() if match else None


def detectar_flags_processuais(texto: str) -> dict[str, bool]:
    """Sinalizadores booleanos — presença de frase específica, nunca um
    palpite: segredo de justiça, justiça gratuita, pedido liminar."""
    texto_norm = _remover_acentos(texto.lower())
    return {
        'segredo_de_justica': 'segredo de justica' in texto_norm,
        'justica_gratuita': 'justica gratuita' in texto_norm or 'gratuidade de justica' in texto_norm,
        'pedido_liminar': 'liminar' in texto_norm,
    }


def processar_mensagem(texto: str) -> dict[str, Any]:
    """Ponto único de entrada: recebe o texto colado e devolve tudo
    estruturado — dados extraídos, CNJ normalizado + tribunal provável,
    divergências e dados faltantes. Nunca inventa o que não conseguiu
    achar no texto."""
    cnj_candidatos = extrair_cnj_candidatos(texto)

    # Acha CPF/CNPJ só no texto SEM os trechos que já viraram CNJ — sem
    # isso, os próprios dígitos do CNJ eram capturados de novo como se
    # fossem um CPF/CNPJ à parte (achado real testando com dado de
    # verdade: "00007659720235070016" continha um CPF "válido" por
    # coincidência de dígitos, mas não era um CPF de verdade).
    texto_sem_cnj = texto
    for candidato in cnj_candidatos:
        texto_sem_cnj = re.sub(r'[\d][\d.\-/\s]{18,34}[\d]', lambda m: '' if only_digits(split_cnj_suffix(m.group(0))[0]) == candidato['cnj'] else m.group(0), texto_sem_cnj)

    cpf = extrair_cpf(texto_sem_cnj)
    cnpj = extrair_cnpj(texto_sem_cnj)
    nome = extrair_nome(texto)
    cidade_uf = extrair_cidade_uf(texto)
    ente_devedor = extrair_ente_devedor(texto)
    classe_documento = detectar_classe_documento(texto)
    eh_requisitorio_precatorio = eh_documento_requisitorio_ou_precatorio(texto)
    valor_causa = extrair_valor_causa(texto)
    orgao_julgador = extrair_orgao_julgador(texto)
    flags = detectar_flags_processuais(texto)
    processo_referencia = extrair_processo_referencia(texto)

    processos_detectados = []
    divergencias = []
    cnj_da_referencia = processo_referencia['cnj'] if processo_referencia else None
    for candidato in cnj_candidatos:
        if candidato['cnj'] == cnj_da_referencia:
            continue  # já aparece na seção própria de processo_referencia, não duplica aqui
        analise = analisar_cnj(candidato['cnj'])
        processos_detectados.append({
            'cnj_original': candidato['cnj'],
            'cnj_normalizado': format_cnj(candidato['cnj']),
            'sufixo': candidato['sufixo'],
            **analise,
        })
        uf_mencionada = cidade_uf.get('uf')
        if uf_mencionada and analise['ufs_cobertas'] and uf_mencionada not in analise['ufs_cobertas']:
            divergencias.append(
                f"Você mencionou {uf_mencionada}, mas o número {format_cnj(candidato['cnj'])} indica "
                f"{analise['tribunal_provavel']} ({analise['segmento_nome']}), que cobre "
                f"{', '.join(analise['ufs_cobertas'])} — não {uf_mencionada}."
            )

    processo_referencia_detalhado = None
    if processo_referencia:
        analise_ref = analisar_cnj(processo_referencia['cnj'])
        processo_referencia_detalhado = {
            'cnj_original': processo_referencia['cnj'],
            'cnj_normalizado': format_cnj(processo_referencia['cnj']),
            'sufixo': processo_referencia['sufixo'],
            **analise_ref,
        }

    dados_faltantes = []
    if not cnj_candidatos:
        dados_faltantes.append('Número do processo/CNJ')
    if not cpf and not cnpj:
        dados_faltantes.append('CPF ou CNPJ')
    if not nome:
        dados_faltantes.append('Nome completo')

    return {
        'texto_original': texto,
        'nome': nome,
        'cpf': cpf,
        'cpf_mascarado': mask_document(cpf) if cpf else None,
        'cnpj': cnpj,
        'cnpj_mascarado': mask_document(cnpj) if cnpj else None,
        'cidade': cidade_uf.get('cidade'),
        'uf': cidade_uf.get('uf'),
        'ente_devedor': ente_devedor,
        'classe_documento': classe_documento,
        'eh_requisitorio_ou_precatorio': eh_requisitorio_precatorio,
        'valor_causa': valor_causa,
        'orgao_julgador': orgao_julgador,
        'segredo_de_justica': flags['segredo_de_justica'],
        'justica_gratuita': flags['justica_gratuita'],
        'pedido_liminar': flags['pedido_liminar'],
        'processos_detectados': processos_detectados,
        'processo_referencia': processo_referencia_detalhado,
        'divergencias': divergencias,
        'dados_faltantes': dados_faltantes,
    }


def gerar_resposta_sugerida(dados: dict[str, Any]) -> str:
    """Monta uma sugestão de resposta pro cliente — sempre um rascunho pra
    revisar antes de enviar, nunca envio automático."""
    if dados.get('classe_documento') == 'Ação Rescisória' and dados.get('processo_referencia'):
        ref = dados['processo_referencia']['cnj_normalizado']
        return (
            'Identificamos que o documento se refere a uma ação rescisória'
            + (f' no {dados["processos_detectados"][0]["tribunal_provavel"]}' if dados.get('processos_detectados') and dados['processos_detectados'][0].get('tribunal_provavel') else '')
            + f' e menciona processo referência ({ref}). Vamos analisar o processo principal e o processo relacionado para verificar impacto sobre eventual crédito.'
        )

    if dados.get('eh_requisitorio_ou_precatorio') and dados['processos_detectados']:
        tribunal = dados['processos_detectados'][0].get('tribunal_provavel')
        return (
            f'Identificamos que o documento é um ofício requisitório/precatório'
            + (f' do {tribunal}' if tribunal else '')
            + '. Vamos confirmar o status junto ao órgão de precatórios do tribunal e retornar com a análise de valor e previsão.'
        )

    if dados['processos_detectados']:
        p = dados['processos_detectados'][0]
        partes = [f'Recebemos as informações. Identificamos o processo nº {p["cnj_normalizado"]}']
        if p.get('tribunal_provavel'):
            partes.append(f', aparentemente vinculado ao {p["tribunal_provavel"]}')
        if dados.get('cidade'):
            partes.append(f'/{dados["uf"]}' if dados.get('uf') else '')
        partes.append('. Vamos analisar a existência de crédito, fase processual e eventual possibilidade de aquisição. Retornaremos na sequência.')
        return ''.join(partes)

    if dados['dados_faltantes']:
        return f'Para avançarmos, poderia nos enviar também {", ".join(dados["dados_faltantes"]).lower()}, e, se tiver, algum documento ou print do processo?'

    return 'Recebemos as informações e vamos analisar. Retornaremos em breve.'
