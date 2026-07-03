from __future__ import annotations

from typing import Any
from .precatorio import classify_precatorio


def _first_subject_name(source: dict) -> str | None:
    assuntos = source.get('assuntos')
    if not isinstance(assuntos, list):
        return None
    names = []
    for item in assuntos:
        if isinstance(item, list):
            for sub in item:
                if isinstance(sub, dict) and sub.get('nome'):
                    names.append(str(sub.get('nome')))
        elif isinstance(item, dict) and item.get('nome'):
            names.append(str(item.get('nome')))
    return '; '.join(names[:5]) or None


def normalize_process_record(item: dict, include_raw: bool = False) -> dict:
    provider = item.get('provider') or 'unknown'
    source: dict[str, Any] = item.get('source') or item.get('raw_hit') or item
    tribunal = source.get('tribunal') or item.get('tribunal')

    classe_obj = source.get('classe') if isinstance(source.get('classe'), dict) else {}
    orgao_obj = source.get('orgaoJulgador') if isinstance(source.get('orgaoJulgador'), dict) else {}

    score, flags = classify_precatorio(source)

    return {
        'provider': provider,
        'tribunal': tribunal,
        'numero_processo': source.get('numeroProcesso') or source.get('numero_processo') or source.get('cnj') or source.get('code'),
        'classe': classe_obj.get('nome') or source.get('classe') or source.get('class_name'),
        'assunto': _first_subject_name(source) or source.get('assunto') or source.get('subject'),
        'orgao_julgador': orgao_obj.get('nome') or source.get('orgao_julgador') or source.get('court_unit'),
        'data_ajuizamento': source.get('dataAjuizamento') or source.get('distribution_date'),
        'ultima_atualizacao': source.get('dataHoraUltimaAtualizacao') or source.get('updated_at') or source.get('@timestamp'),
        'precatorio_score': score,
        'precatorio_flags': flags,
        'raw': item if include_raw else None,
    }
