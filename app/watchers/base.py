"""v32 — Interface comum dos watchers. Cada watcher devolve um
WatcherResult padronizado; o scheduler decide o que fazer com isso
(salvar WatcherRun, PublicationHit, criar OpportunityLead)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HitEncontrado:
    """Um "achado" bruto de um watcher — vira PublicationHit."""
    source: str
    tribunal: str | None
    publication_date: str | None
    process_number: str | None
    normalized_cnj: str | None
    parties_text: str | None
    lawyers_text: str | None
    publication_text: str
    matched_terms: list[str] = field(default_factory=list)
    signal_type: str | None = None
    confidence: str = 'medium'
    source_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class WatcherResult:
    watcher_name: str
    status: str  # completed|partial|failed
    date_from: str | None = None
    date_to: str | None = None
    tribunals_scanned: list[str] = field(default_factory=list)
    total_publications: int = 0
    hits: list[HitEncontrado] = field(default_factory=list)
    error: str | None = None
