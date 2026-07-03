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
