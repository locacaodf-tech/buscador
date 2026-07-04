import re


def normalize_cnj(value: str | None) -> str:
    return re.sub(r'\D+', '', value or '')


def format_cnj(value: str | None) -> str:
    n = normalize_cnj(value)
    if len(n) != 20:
        return value or ''
    return f'{n[0:7]}-{n[7:9]}.{n[9:13]}.{n[13]}.{n[14:16]}.{n[16:20]}'


def looks_like_cnj(value: str | None) -> bool:
    return len(normalize_cnj(value)) == 20


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
    mapa = {'01': 'TRF1', '02': 'TRF2', '03': 'TRF3', '04': 'TRF4', '05': 'TRF5', '06': 'TRF6'}
    return mapa.get(tribunal_codigo)
