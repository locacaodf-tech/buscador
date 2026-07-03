# Aliases oficiais do DataJud. Use siglas em maiúsculas na entrada.
# A API usa api_publica_<alias>/_search.

TRIBUNAL_ALIASES: dict[str, str] = {
    # Superiores
    'TST': 'tst', 'TSE': 'tse', 'STJ': 'stj', 'STM': 'stm',
    # Justiça Federal
    'TRF1': 'trf1', 'TRF2': 'trf2', 'TRF3': 'trf3', 'TRF4': 'trf4', 'TRF5': 'trf5', 'TRF6': 'trf6',
    # Justiça Estadual
    'TJAC': 'tjac', 'TJAL': 'tjal', 'TJAM': 'tjam', 'TJAP': 'tjap', 'TJBA': 'tjba', 'TJCE': 'tjce',
    'TJDFT': 'tjdft', 'TJES': 'tjes', 'TJGO': 'tjgo', 'TJMA': 'tjma', 'TJMG': 'tjmg', 'TJMS': 'tjms',
    'TJMT': 'tjmt', 'TJPA': 'tjpa', 'TJPB': 'tjpb', 'TJPE': 'tjpe', 'TJPI': 'tjpi', 'TJPR': 'tjpr',
    'TJRJ': 'tjrj', 'TJRN': 'tjrn', 'TJRO': 'tjro', 'TJRR': 'tjrr', 'TJRS': 'tjrs', 'TJSC': 'tjsc',
    'TJSE': 'tjse', 'TJSP': 'tjsp', 'TJTO': 'tjto',
    # Justiça do Trabalho
    **{f'TRT{i}': f'trt{i}' for i in range(1, 25)},
    # Justiça Eleitoral - padrão DataJud usa hífen
    'TREAC': 'tre-ac', 'TREAL': 'tre-al', 'TREAM': 'tre-am', 'TREAP': 'tre-ap', 'TREBA': 'tre-ba',
    'TRECE': 'tre-ce', 'TREDFT': 'tre-dft', 'TREES': 'tre-es', 'TREGO': 'tre-go', 'TREMA': 'tre-ma',
    'TREMG': 'tre-mg', 'TREMS': 'tre-ms', 'TREMT': 'tre-mt', 'TREPA': 'tre-pa', 'TREPB': 'tre-pb',
    'TREPE': 'tre-pe', 'TREPI': 'tre-pi', 'TREPR': 'tre-pr', 'TRERJ': 'tre-rj', 'TRERN': 'tre-rn',
    'TRERO': 'tre-ro', 'TRERR': 'tre-rr', 'TRERS': 'tre-rs', 'TRESC': 'tre-sc', 'TRESE': 'tre-se',
    'TRESP': 'tre-sp', 'TRETO': 'tre-to',
    # Justiça Militar estadual
    'TJMMG': 'tjmmg', 'TJMRS': 'tjmrs', 'TJMSP': 'tjmsp',
}

DEFAULT_PRECAT_TRIBUNALS = ['TRF1', 'TRF2', 'TRF3', 'TRF4', 'TRF5', 'TRF6', 'TJDFT', 'TJSP', 'TJRJ', 'TJMG', 'TJGO']
FEDERAL_TRIBUNALS = ['TRF1', 'TRF2', 'TRF3', 'TRF4', 'TRF5', 'TRF6']
ALL_TRIBUNALS = list(TRIBUNAL_ALIASES.keys())


def normalize_tribunals(tribunals: list[str] | None, default: list[str] | None = None) -> list[str]:
    if not tribunals:
        return default or FEDERAL_TRIBUNALS
    out: list[str] = []
    for item in tribunals:
        sigla = item.strip().upper().replace('-', '').replace(' ', '')
        if sigla in TRIBUNAL_ALIASES:
            out.append(sigla)
    return out or (default or FEDERAL_TRIBUNALS)
