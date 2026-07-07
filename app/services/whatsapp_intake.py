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

from ..utils.cnj import normalize_cnj, format_cnj, infer_tribunal_from_cnj
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


def extrair_cnj_candidatos(texto: str) -> list[str]:
    """Acha número CNJ dentro de texto livre, mesmo mal formatado (com
    ponto em vez de hífen, sem nenhuma pontuação, etc.) — busca qualquer
    sequência de 20 dígitos, ignorando pontuação no meio."""
    candidatos = []
    # Primeiro tenta o padrão formatado clássico (com ou sem pontuação
    # correta), depois cai pro fallback de "20 dígitos em sequência".
    for match in re.finditer(r'[\d][\d.\-/\s]{18,30}[\d]', texto):
        digitos = only_digits(match.group(0))
        if len(digitos) == 20 and digitos not in candidatos:
            candidatos.append(digitos)
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
    for i, cnj_raw in enumerate(cnj_candidatos):
        marcador = f'\x00CNJ{i}\x00'
        # acha o trecho exato (com pontuação original, se houver) que gerou esse CNJ
        for match in re.finditer(r'[\d][\d.\-/\s]{18,30}[\d]', protegido):
            if only_digits(match.group(0)) == cnj_raw and match.group(0) not in marcadores.values():
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
    for cnj_raw in cnj_candidatos:
        texto_sem_cnj = re.sub(re.escape(cnj_raw), '', texto_sem_cnj)
        # também remove a versão pontuada, caso o texto original já viesse formatado
        texto_sem_cnj = re.sub(r'[\d][\d.\-/\s]{18,30}[\d]', lambda m: '' if only_digits(m.group(0)) == cnj_raw else m.group(0), texto_sem_cnj)

    cpf = extrair_cpf(texto_sem_cnj)
    cnpj = extrair_cnpj(texto_sem_cnj)
    nome = extrair_nome(texto)
    cidade_uf = extrair_cidade_uf(texto)
    ente_devedor = extrair_ente_devedor(texto)

    processos_detectados = []
    divergencias = []
    for cnj_raw in cnj_candidatos:
        analise = analisar_cnj(cnj_raw)
        processos_detectados.append({
            'cnj_original': cnj_raw,
            'cnj_normalizado': format_cnj(cnj_raw),
            **analise,
        })
        uf_mencionada = cidade_uf.get('uf')
        if uf_mencionada and analise['ufs_cobertas'] and uf_mencionada not in analise['ufs_cobertas']:
            divergencias.append(
                f"Você mencionou {uf_mencionada}, mas o número {format_cnj(cnj_raw)} indica "
                f"{analise['tribunal_provavel']} ({analise['segmento_nome']}), que cobre "
                f"{', '.join(analise['ufs_cobertas'])} — não {uf_mencionada}."
            )

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
        'processos_detectados': processos_detectados,
        'divergencias': divergencias,
        'dados_faltantes': dados_faltantes,
    }


def gerar_resposta_sugerida(dados: dict[str, Any]) -> str:
    """Monta uma sugestão de resposta pro cliente — sempre um rascunho pra
    revisar antes de enviar, nunca envio automático."""
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
