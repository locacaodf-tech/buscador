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
    provider: str = typer.Option('auto', help='auto, multi, datajud, tribunal_precatorios'),
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


@app.command()
def bootstrap_admin(
    email: str = typer.Option(..., prompt=True, help='E-mail do primeiro administrador'),
    full_name: str = typer.Option(..., prompt=True, help='Nome completo'),
    password: str = typer.Option(..., prompt=True, hide_input=True, confirmation_prompt=True, help='Senha do primeiro administrador'),
    tenant_slug: str = typer.Option('meuprecatoriobr', help='Slug do tenant operacional'),
    tenant_nome: str = typer.Option('MeuPrecatórioBR', help='Nome do tenant operacional'),
):
    """v36 — Cria o PRIMEIRO administrador. Só existe via CLI/bootstrap —
    nunca via endpoint público (achado real de auditoria: o BuyerRadar
    original tinha /register público aceitando qualquer role). Rodar de
    novo com um tenant que já existe e um admin que já existe não duplica
    nada — é seguro rodar mais de uma vez."""
    from app.db import SessionLocal, init_db
    from app.models_auth import Tenant, User, UserRole
    from app.services.auth import hash_password

    email = email.strip().lower()
    init_db()
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
        if not tenant:
            tenant = Tenant(slug=tenant_slug, nome=tenant_nome)
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            print(f'[green]Tenant criado:[/green] {tenant.nome} ({tenant.id})')
        else:
            print(f'[yellow]Tenant já existia:[/yellow] {tenant.nome} ({tenant.id})')

        existente = db.query(User).filter(User.tenant_id == tenant.id, User.email == email).first()
        if existente:
            print(f'[red]Já existe um usuário com esse e-mail neste tenant:[/red] {email} (papel atual: {existente.role.value})')
            raise typer.Exit(code=1)

        admin = User(
            tenant_id=tenant.id, email=email, hashed_password=hash_password(password),
            full_name=full_name, role=UserRole.ADMINISTRADOR, is_active=True,
        )
        db.add(admin)
        db.commit()
        print(f'[green]Administrador criado com sucesso:[/green] {email} — papel: administrador')
    finally:
        db.close()


@app.command()
def migrate_buyerradar(
    source: str = typer.Option(..., help='DATABASE_URL do banco de origem do BuyerRadar (sqlite:/// ou postgresql://)'),
    dry_run: bool = typer.Option(True, help='So relatar o que aconteceria, sem gravar nada. Use --no-dry-run pra aplicar de verdade.'),
    tenant_slug: str = typer.Option('meuprecatoriobr', help='Tenant de destino'),
):
    """v36 - Importa organizations/funds/people/contacts do banco de
    origem do BuyerRadar pra dentro do Buscador de Processos unificado.
    SEMPRE roda em modo --dry-run por padrao."""
    from sqlalchemy import create_engine, text
    from app.db import SessionLocal, init_db
    from app.models_auth import Tenant
    from app.models_buyerradar import Organization, Fund, Person, Contact
    import uuid as uuid_mod

    init_db()
    db = SessionLocal()
    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
    if not tenant:
        print(f'[red]Tenant "{tenant_slug}" nao existe. Rode "bootstrap-admin" primeiro.[/red]')
        raise typer.Exit(code=1)

    try:
        origem_engine = create_engine(source)
        origem_conn = origem_engine.connect()
    except Exception as exc:
        print(f'[red]Nao consegui conectar na origem "{source}": {exc}[/red]')
        raise typer.Exit(code=1)

    relatorio = {
        'tabelas_existentes': [], 'registros_existentes': {}, 'novos': {}, 'duplicados': {},
        'conflitos': [], 'campos_sem_correspondencia': [], 'erros': [],
    }

    TABELAS_ORIGEM_PARA_MODELO = {
        'organizations': (Organization, 'cnpj'),
        'funds': (Fund, 'cnpj'),
        'people': (Person, None),
        'contacts': (Contact, 'email'),
    }

    query_tabelas = (
        "SELECT name FROM sqlite_master WHERE type='table'" if source.startswith('sqlite')
        else "SELECT tablename AS name FROM pg_tables WHERE schemaname='public'"
    )
    linhas_tabelas = origem_conn.execute(text(query_tabelas)).fetchall()
    tabelas_na_origem = {row[0] for row in linhas_tabelas}
    relatorio['tabelas_existentes'] = sorted(tabelas_na_origem)

    for nome_tabela, (Modelo, campo_unico) in TABELAS_ORIGEM_PARA_MODELO.items():
        if nome_tabela not in tabelas_na_origem:
            relatorio['campos_sem_correspondencia'].append(f'{nome_tabela}: nao existe na origem, pulado.')
            continue
        try:
            linhas = origem_conn.execute(text(f'SELECT * FROM {nome_tabela}')).mappings().all()
        except Exception as exc:
            relatorio['erros'].append(f'{nome_tabela}: erro ao ler - {exc}')
            continue

        relatorio['registros_existentes'][nome_tabela] = len(linhas)
        novos, duplicados = 0, 0
        for linha in linhas:
            valor_chave = linha.get(campo_unico) if campo_unico else None
            ja_existe = False
            if campo_unico and valor_chave:
                ja_existe = db.query(Modelo).filter(getattr(Modelo, campo_unico) == valor_chave, Modelo.tenant_id == tenant.id).first() is not None
            if ja_existe:
                duplicados += 1
                continue
            novos += 1
            if not dry_run:
                campos_validos = {c.name for c in Modelo.__table__.columns}
                dados = {k: v for k, v in dict(linha).items() if k in campos_validos and k not in {'id', 'tenant_id'}}
                db.add(Modelo(id=str(uuid_mod.uuid4()), tenant_id=tenant.id, **dados))
        relatorio['novos'][nome_tabela] = novos
        relatorio['duplicados'][nome_tabela] = duplicados

    if not dry_run:
        db.commit()
        print('[green]Migracao aplicada de verdade (--no-dry-run).[/green]')
    else:
        db.rollback()
        print('[yellow]DRY RUN - nada foi gravado. Rode com --no-dry-run pra aplicar de verdade.[/yellow]')

    print(json.dumps(relatorio, ensure_ascii=False, indent=2, default=str))
    origem_conn.close()
    db.close()


if __name__ == '__main__':
    app()
