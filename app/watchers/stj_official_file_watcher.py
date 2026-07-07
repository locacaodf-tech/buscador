"""v32 — STJ Official File Watcher: reaproveita o sync do StjBot (v30.2)
pra ver se saíram arquivos novos do STJ desde a última vez, e gera hits
pra registros que ainda não tínhamos visto (comparados por hash de
arquivo + sequencial)."""
from __future__ import annotations

from typing import Any

from .base import HitEncontrado, WatcherResult


async def varrer_arquivos_stj(db) -> WatcherResult:
    """Roda a sincronização oficial do STJ (mesma função da v30.2) e
    compara os arquivos baixados agora com os que já tínhamos — só gera
    hit pra sequencial que apareceu de novo desde a última rodada."""
    from ..services.stj_official_scraper import sync_official_files
    from ..models import StjOfficialFile

    hashes_ja_conhecidos = {f.file_hash for f in db.query(StjOfficialFile).filter(StjOfficialFile.status == 'downloaded').all() if f.file_hash}

    resultado_sync = await sync_official_files(db)
    if resultado_sync['status'] != 'ok':
        return WatcherResult(
            watcher_name='stj_official_file_watcher', status='failed',
            total_publications=0, hits=[],
            error=resultado_sync.get('erro_pagina') or f"Sync retornou: {resultado_sync['status']}",
        )

    arquivos_novos = [
        a for a in resultado_sync['arquivos_processados']
        if a['status'] == 'downloaded'
    ]
    # Só considera "novo de verdade" arquivo cujo hash não estava no banco
    # ANTES desta rodada (evita marcar tudo como novo toda vez que sync roda).
    registros_stj = db.query(StjOfficialFile).filter(StjOfficialFile.status == 'downloaded').all()
    hits: list[HitEncontrado] = []
    for registro in registros_stj:
        if registro.file_hash and registro.file_hash not in hashes_ja_conhecidos:
            hits.append(HitEncontrado(
                source='stj_official_file_watcher', tribunal='STJ', publication_date=None,
                process_number=None, normalized_cnj=None, parties_text=None, lawyers_text=None,
                publication_text=f'Novo arquivo oficial do STJ: {registro.original_filename} ({registro.row_count or 0} registros).',
                matched_terms=['precatorio'], signal_type='precatorio_confirmado', confidence='high',
                source_url=registro.source_url,
                raw={'arquivo': registro.original_filename, 'ano': registro.year},
            ))

    return WatcherResult(
        watcher_name='stj_official_file_watcher', status='completed',
        tribunals_scanned=['STJ'], total_publications=len(arquivos_novos), hits=hits,
    )
