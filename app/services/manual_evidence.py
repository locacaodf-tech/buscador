from __future__ import annotations

import re
from pathlib import Path
from datetime import datetime, timezone

from ..config import get_settings

EVIDENCE_DIR = Path('data/evidencias_manuais')  # fallback local/testes
ALLOWED_EXTENSIONS = {'.pdf', '.xlsx', '.xls', '.png', '.jpg', '.jpeg'}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class InvalidEvidenceFile(ValueError):
    pass


def _sanitize_filename(name: str) -> str:
    name = Path(name).name
    name = re.sub(r'[^A-Za-z0-9._-]+', '_', name)
    return name or 'evidencia'


def evidence_dir() -> Path:
    """Prioriza EVIDENCE_UPLOAD_DIR do settings (ex.: /data/evidencias_manuais
    no Render com disco persistente); sem isso, usa a pasta local do projeto."""
    configured = getattr(get_settings(), 'evidence_upload_dir', '')
    return Path(configured) if configured else EVIDENCE_DIR


def ensure_evidence_dir() -> Path:
    directory = evidence_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save_evidence_file(original_filename: str, content: bytes) -> tuple[str, str]:
    """Salva o arquivo anexado (PDF/XLSX/print) numa pasta controlada.
    Devolve (nome_original, caminho_salvo)."""
    ext = Path(original_filename or '').suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise InvalidEvidenceFile(f'Extensão "{ext}" não permitida. Use PDF, XLSX, XLS, PNG ou JPG.')
    if len(content) > MAX_UPLOAD_BYTES:
        raise InvalidEvidenceFile(f'Arquivo maior que o limite de {MAX_UPLOAD_BYTES // (1024 * 1024)}MB.')
    directory = ensure_evidence_dir()
    safe_name = _sanitize_filename(original_filename)
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    stored_name = f'{timestamp}__{safe_name}'
    stored_path = directory / stored_name
    stored_path.write_bytes(content)
    return original_filename, str(stored_path)
