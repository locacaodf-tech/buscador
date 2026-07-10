import re


def only_digits(value: str | None) -> str:
    return re.sub(r'\D+', '', value or '')


def mask_document(value: str | None) -> str:
    digits = only_digits(value)
    if len(digits) == 11:
        return f'{digits[:3]}.***.***-{digits[-2:]}'
    if len(digits) == 14:
        return f'{digits[:2]}.***.***/****-{digits[-2:]}'
    if len(digits) > 6:
        return f'{digits[:3]}***{digits[-3:]}'
    if value:
        return value[:3] + '***'
    return ''


def is_valid_cpf_basic(value: str) -> bool:
    digits = only_digits(value)
    if len(digits) != 11 or len(set(digits)) == 1:
        return False

    def calc_digit(part: str) -> str:
        s = sum(int(d) * weight for d, weight in zip(part, range(len(part) + 1, 1, -1)))
        r = (s * 10) % 11
        return '0' if r == 10 else str(r)

    return digits[-2] == calc_digit(digits[:9]) and digits[-1] == calc_digit(digits[:10])


def hash_document(value: str | None) -> str | None:
    """Hash salgado de CPF/CNPJ — pra buscar por documento sem guardar o
    número em claro em nenhum lugar. Usa o salt configurado em
    INDICE_CPF_HASH_SALT (ver app/config.py); nunca reversível."""
    import hashlib
    from ..config import get_settings
    digitos = only_digits(value)
    if not digitos:
        return None
    salt = get_settings().indice_cpf_hash_salt
    return hashlib.sha256((salt + digitos).encode('utf-8')).hexdigest()
