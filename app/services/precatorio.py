from typing import Any

# SisPreq/PDPJ e TPU: classes, movimentos e assuntos de precatório/RPV.
PRECAT_RPV_CLASS_CODES = {1265, 1266, 1040, 1677}
PRECAT_RPV_MOVEMENT_CODES = {
    12457, 15247, 15248,
    12177, 12174, 12176, 12175, 12178, 12179,
    12170, 12167, 12169, 12168, 12171, 12172,
}
PRECAT_RPV_SUBJECT_CODES = {14855, 13285, 13506}

PAID_MOVEMENTS = {12169, 12176}
CANCELLED_MOVEMENTS = {12170, 12177}
SENT_TO_COURT_MOVEMENTS = {12167, 12174}
PREPARED_MOVEMENTS = {12168, 12175}
SUSPENDED_MOVEMENTS = {12172, 12179, 15247, 15248}


def _get_nested_code(obj: dict, path: str) -> int | None:
    current: Any = obj
    for part in path.split('.'):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    try:
        return int(current) if current is not None else None
    except Exception:
        return None


def _codes_from_list(items: Any) -> set[int]:
    codes: set[int] = set()
    if not isinstance(items, list):
        return codes
    for item in items:
        if isinstance(item, list):
            codes |= _codes_from_list(item)
            continue
        if isinstance(item, dict) and item.get('codigo') is not None:
            try:
                codes.add(int(item['codigo']))
            except Exception:
                pass
    return codes


def classify_precatorio(source: dict) -> tuple[int, list[str]]:
    """Score simples para destacar processos com sinais de precatório/RPV.

    0 = sem indício; 100+ = muito forte. Não substitui análise humana.
    """
    flags: list[str] = []
    score = 0

    class_code = _get_nested_code(source, 'classe.codigo')
    class_name = ((source.get('classe') or {}).get('nome') or '').lower()
    subject_codes = _codes_from_list(source.get('assuntos'))
    movement_codes = _codes_from_list(source.get('movimentos'))

    if class_code in PRECAT_RPV_CLASS_CODES or 'precat' in class_name or 'requisição de pequeno valor' in class_name:
        score += 50
        flags.append('classe_precatorio_ou_rpv')

    if subject_codes & PRECAT_RPV_SUBJECT_CODES:
        score += 25
        flags.append('assunto_precatorio_ou_rpv')

    if movement_codes & PRECAT_RPV_MOVEMENT_CODES:
        score += 40
        flags.append('movimento_precatorio_ou_rpv')

    if movement_codes & SENT_TO_COURT_MOVEMENTS:
        score += 15
        flags.append('requisicao_enviada_ao_tribunal')

    if movement_codes & PREPARED_MOVEMENTS:
        score += 10
        flags.append('requisicao_preparada_para_envio')

    if movement_codes & PAID_MOVEMENTS:
        score -= 30
        flags.append('consta_movimento_pago')

    if movement_codes & CANCELLED_MOVEMENTS:
        score -= 40
        flags.append('consta_movimento_cancelado')

    if movement_codes & SUSPENDED_MOVEMENTS:
        score -= 10
        flags.append('consta_suspensao_sobrestamento')

    # Sinais textuais em assuntos/movimentos, caso o tribunal indexe códigos de forma irregular.
    text = ' '.join([
        class_name,
        ' '.join(str((a or {}).get('nome', '')).lower() for a in source.get('assuntos', []) if isinstance(a, dict)),
        ' '.join(str((m or {}).get('nome', '')).lower() for m in source.get('movimentos', []) if isinstance(m, dict)),
    ])
    if 'precatório' in text or 'precatorio' in text:
        score += 20
        flags.append('texto_menciona_precatorio')
    if 'rpv' in text or 'pequeno valor' in text:
        score += 20
        flags.append('texto_menciona_rpv')

    return max(score, 0), sorted(set(flags))


def build_precatorio_query(size: int = 50, search_after: list | None = None) -> dict:
    query: dict = {
        'size': size,
        'query': {
            'bool': {
                'should': [
                    {'terms': {'classe.codigo': sorted(PRECAT_RPV_CLASS_CODES)}},
                    {'terms': {'movimentos.codigo': sorted(PRECAT_RPV_MOVEMENT_CODES)}},
                    {'terms': {'assuntos.codigo': sorted(PRECAT_RPV_SUBJECT_CODES)}},
                    {'match_phrase': {'classe.nome': 'Precatório'}},
                    {'match_phrase': {'classe.nome': 'Requisição de Pequeno Valor'}},
                ],
                'minimum_should_match': 1,
            }
        },
        'sort': [{'@timestamp': {'order': 'desc'}}],
    }
    if search_after:
        query['search_after'] = search_after
    return query
