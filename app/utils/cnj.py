import re


def split_cnj_suffix(value: str | None) -> tuple[str, str | None]:
    """Separa um CNJ do sufixo/incidente que às vezes vem colado no final
    (ex.: '0016114-59.2017.8.26.0053/01' — o '/01' indica um incidente,
    desdobramento ou volume vinculado ao processo principal, não faz
    parte do número CNJ em si). Devolve (cnj_sem_sufixo, sufixo_ou_None).

    Achado real: sem essa separação, normalize_cnj colava os dígitos do
    sufixo direto no CNJ (virando 22 dígitos em vez de 20), quebrando a
    inferência de tribunal por completo pra qualquer CNJ com sufixo."""
    texto = (value or '').strip()
    match = re.search(r'^(.*\d)\s*/\s*(\d{1,3})\s*$', texto)
    if match:
        return match.group(1), match.group(2)
    return texto, None


def normalize_cnj(value: str | None) -> str:
    base, _ = split_cnj_suffix(value)
    return re.sub(r'\D+', '', base)


def format_cnj(value: str | None) -> str:
    n = normalize_cnj(value)
    if len(n) != 20:
        return value or ''
    return f'{n[0:7]}-{n[7:9]}.{n[9:13]}.{n[13]}.{n[14:16]}.{n[16:20]}'


def looks_like_cnj(value: str | None) -> bool:
    return len(normalize_cnj(value)) == 20


FEDERAL_TR_MAP = {'01': 'TRF1', '02': 'TRF2', '03': 'TRF3', '04': 'TRF4', '05': 'TRF5', '06': 'TRF6'}

# Numeração oficial dos TRTs (Justiça do Trabalho, segmento "5"), confirmada
# no Portal do CNJ (cnj.jus.br/poder-judiciario/tribunais/) em 2026-07-06.
TRABALHISTA_TR_MAP = {f'{i:02d}': f'TRT{i}' for i in range(1, 25)}

# Ordem alfabética oficial da Justiça Estadual (segmento "8"), conforme a
# própria estrutura definida pelo CNJ (Resolução 65/2008): cada TJ recebeu um
# número de 01 a 27 seguindo a ordem alfabética dos estados. Fonte pública,
# confirmada em mais de uma referência (ex.: numeração 819 = TJRJ, 826 = TJSP).
ESTADUAL_TR_MAP = {
    '01': 'TJAC', '02': 'TJAL', '03': 'TJAP', '04': 'TJAM', '05': 'TJBA',
    '06': 'TJCE', '07': 'TJDFT', '08': 'TJES', '09': 'TJGO', '10': 'TJMA',
    '11': 'TJMT', '12': 'TJMS', '13': 'TJMG', '14': 'TJPA', '15': 'TJPB',
    '16': 'TJPR', '17': 'TJPE', '18': 'TJPI', '19': 'TJRJ', '20': 'TJRN',
    '21': 'TJRS', '22': 'TJRO', '23': 'TJRR', '24': 'TJSC', '25': 'TJSE',
    '26': 'TJSP', '27': 'TJTO',
}


def infer_federal_tribunal(value: str | None) -> str | None:
    """O próprio número CNJ (padrão NNNNNNN-DD.AAAA.J.TR.OOOO) já indica o
    tribunal: o dígito J=4 é Justiça Federal, e TR de 01 a 06 é o TRF
    correspondente. Evita consultar os 6 TRFs à toa quando o número já diz
    qual é o certo. Devolve None se não for possível inferir (não é CNJ
    válido, não é da Justiça Federal, ou o código de TR não é 01-06)."""
    n = normalize_cnj(value)
    if len(n) != 20:
        return None
    segmento = n[13]
    tribunal_codigo = n[14:16]
    if segmento != '4':
        return None
    return FEDERAL_TR_MAP.get(tribunal_codigo)


def infer_tribunal_from_cnj(value: str | None) -> str | None:
    """Versão mais ampla: infere o tribunal provável pra Justiça Federal
    (segmento 4), Justiça do Trabalho (segmento 5) ou Justiça Estadual/DF
    (segmento 8), a partir dos próprios dígitos do CNJ. Pra outros
    segmentos (eleitoral, militar, tribunais superiores), devolve None —
    não são cobertos ainda."""
    n = normalize_cnj(value)
    if len(n) != 20:
        return None
    segmento = n[13]
    tribunal_codigo = n[14:16]
    if segmento == '4':
        return FEDERAL_TR_MAP.get(tribunal_codigo)
    if segmento == '5':
        return TRABALHISTA_TR_MAP.get(tribunal_codigo)
    if segmento == '8':
        return ESTADUAL_TR_MAP.get(tribunal_codigo)
    return None
