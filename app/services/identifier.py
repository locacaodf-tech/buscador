from __future__ import annotations

import re
from dataclasses import dataclass

from ..utils.cpf import only_digits
from ..utils.cnj import normalize_cnj, split_cnj_suffix


SUPPORTED_SEARCH_TYPES = {
    'auto',
    'cnj',
    'numero_processo',
    'cpf',
    'cnpj',
    'oab',
    'name',
    'requisitorio_number',
    'precatorio_number',
    'rpv_number',
    'precatorio_scan',
    'entidade_devedora',
    'unknown',
}

# Aliases que podem vir do frontend, Claude, planilha, API de tribunal ou payload manual.
SEARCH_TYPE_ALIASES: dict[str, str] = {
    'processo': 'numero_processo',
    'numero_processo': 'numero_processo',
    'n_processo': 'numero_processo',
    'numero_cnj': 'cnj',
    'cnj': 'cnj',
    'cpf': 'cpf',
    'cnpj': 'cnpj',
    'nome': 'name',
    'name': 'name',
    'parte': 'name',
    'oab': 'oab',
    'requisitorio': 'requisitorio_number',
    'requisitorio_number': 'requisitorio_number',
    'numero_requisitorio': 'requisitorio_number',
    'precatório': 'precatorio_number',
    'precatorio': 'precatorio_number',
    'precatorio_number': 'precatorio_number',
    'numero_precatorio': 'precatorio_number',
    'rpv': 'rpv_number',
    'rpv_number': 'rpv_number',
    'numero_rpv': 'rpv_number',
    'precatorio_scan': 'precatorio_scan',
}


@dataclass(frozen=True)
class ResolvedIdentifier:
    search_type: str
    search_key: str
    confidence: str = 'explicit'
    notes: tuple[str, ...] = ()
    sufixo: str | None = None


def normalize_search_type(value: str | None) -> str:
    raw = (value or 'auto').strip().lower().replace('-', '_').replace(' ', '_')
    return SEARCH_TYPE_ALIASES.get(raw, raw if raw in SUPPORTED_SEARCH_TYPES else 'unknown')


def normalize_identifier_value(search_type: str, value: str | None) -> str:
    value = (value or '').strip()
    normalized_type = normalize_search_type(search_type)
    if normalized_type in {'cnj', 'numero_processo'}:
        digits = normalize_cnj(value)
        return digits if len(digits) == 20 else value
    if normalized_type in {'cpf', 'cnpj'}:
        return only_digits(value)
    return value


def infer_identifier(value: str | None, explicit_type: str = 'auto') -> ResolvedIdentifier:
    key = (value or '').strip()
    requested = normalize_search_type(explicit_type)

    if requested != 'auto':
        return ResolvedIdentifier(requested, normalize_identifier_value(requested, key), 'explicit')

    # Achado real de auditoria: essa é a função central usada por
    # /api/diligencia, /api/bots/run, /api/search e a tela "Analisar
    # processo por CNJ" — o fix de sufixo (/01, incidente/desdobramento)
    # tinha sido aplicado só no IntakeBot (whatsapp_intake.py), nunca
    # aqui. normalize_cnj já separa e descarta o sufixo antes de contar
    # dígitos; só precisamos capturar o sufixo separadamente pra exibir.
    _cnj_base, sufixo = split_cnj_suffix(key)
    digits = normalize_cnj(key)
    lower = key.lower()
    notes: list[str] = []

    if len(digits) == 20:
        return ResolvedIdentifier('cnj', digits, 'high', ('20 dígitos: formato típico de número CNJ.',), sufixo=sufixo)

    if len(digits) == 11:
        return ResolvedIdentifier('cpf', digits, 'medium', ('11 dígitos: tratado como CPF; valide se também não é outro identificador interno.',))

    if len(digits) == 14:
        return ResolvedIdentifier('cnpj', digits, 'medium', ('14 dígitos: tratado como CNPJ.',))

    # OAB costuma vir com UF + número ou número + UF. Não dá para validar universalmente sem UF.
    if re.search(r'\boab\b', lower) or re.search(r'^[a-z]{2}\s*\d{3,8}$', lower) or re.search(r'^\d{3,8}\s*[a-z]{2}$', lower):
        return ResolvedIdentifier('oab', key.upper(), 'medium', ('Formato aparenta inscrição OAB; algumas APIs exigem UF separada em extra_params.uf.',))

    if 'rpv' in lower:
        return ResolvedIdentifier('rpv_number', key, 'medium', ('Texto contém RPV; cada tribunal pode exigir número próprio, CNJ ou CPF do credor.',))

    if 'precat' in lower or 'prc' in lower:
        return ResolvedIdentifier('precatorio_number', key, 'medium', ('Texto sugere número de precatório; o formato varia por tribunal.',))

    if 'req' in lower or 'requisit' in lower:
        return ResolvedIdentifier('requisitorio_number', key, 'medium', ('Texto sugere número de requisitório; o formato varia por tribunal.',))

    if digits and not re.search(r'[a-zA-ZÀ-ÿ]', key):
        notes.append('Número sem formato CNJ/CPF/CNPJ. Pode ser requisitório, precatório, RPV, ID interno ou número antigo do tribunal.')
        return ResolvedIdentifier('unknown', key, 'low', tuple(notes))

    return ResolvedIdentifier('name', key, 'low', ('Sem padrão numérico reconhecido; tratado como nome/parte.',))
