import asyncio
import json
from typing import Optional

import typer
from rich import print

from app.db import SessionLocal, init_db
from app.schemas import SearchRequest
from app.services.orchestrator import ProcessLookupOrchestrator, provider_capabilities

app = typer.Typer(help='CLI interna para buscar processos, precatórios, RPVs e requisitórios.')


@app.command()
def search(
    key: str = typer.Argument(..., help='CPF/CNPJ/nome/OAB/CNJ/processo/requisitório/precatório/RPV'),
    search_type: str = typer.Option('auto', help='auto, cnj, numero_processo, cpf, cnpj, name, oab, requisitorio_number, precatorio_number, rpv_number'),
    provider: str = typer.Option('auto', help='auto, multi, datajud, judit, tribunal_precatorios'),
    tribunals: str = typer.Option('', help='Lista separada por vírgula. Ex.: TRF1,TRF3,TJDFT'),
    max_results: int = typer.Option(50),
    precatorio_only: bool = typer.Option(False),
    extra_params: Optional[str] = typer.Option(None, help='JSON com campos extras exigidos pela API. Ex.: {"uf":"DF","ano_orcamento":2027}'),
):
    init_db()
    parsed_extra = json.loads(extra_params) if extra_params else {}
    req = SearchRequest(
        search_key=key,
        search_type=search_type,
        provider=provider,
        tribunals=[t.strip() for t in tribunals.split(',') if t.strip()],
        max_results=max_results,
        precatorio_only=precatorio_only,
        extra_params=parsed_extra,
    )
    with SessionLocal() as db:
        resp = asyncio.run(ProcessLookupOrchestrator(db).search(req))
    print(json.dumps(resp.model_dump(), ensure_ascii=False, indent=2))


@app.command()
def scan_precatorios(
    tribunals: str = typer.Option('TRF1,TRF2,TRF3,TRF4,TRF5,TRF6', help='Tribunais separados por vírgula'),
    max_results: int = typer.Option(100),
):
    init_db()
    req = SearchRequest(
        search_type='precatorio_scan',
        provider='datajud',
        tribunals=[t.strip() for t in tribunals.split(',') if t.strip()],
        max_results=max_results,
        precatorio_only=True,
    )
    with SessionLocal() as db:
        resp = asyncio.run(ProcessLookupOrchestrator(db).search(req))
    print(json.dumps(resp.model_dump(), ensure_ascii=False, indent=2))


@app.command()
def capabilities():
    """Mostra quais identificadores cada conector aceita e quais campos extras pode exigir."""
    print(json.dumps(provider_capabilities(), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    app()
