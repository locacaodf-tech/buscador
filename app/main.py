from __future__ import annotations

import hmac
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .auth import SESSION_COOKIE_NAME, create_session_token, verify_session_token
from .config import get_settings, parse_allowed_origins
from .db import get_db, init_db
from .schemas import SearchRequest, SearchResponse, OfficialPrecatorioPlanRequest, DossierRequest, BrowserSearchRequest, StjSearchRequest, CertificatePlanRequest, CertificateRequestInput, PortalAutomationStartRequest, PortalAutomationSolveRequest
from .services import stj_uploads
from .services import certificate_center
from .services import source_master
from .services import captcha_relay
from .services import manual_evidence
from .models import CertificateRecord, ManualEvidence
from .services.portal_automation import PORTAL_AUTOMATION_STUBS
from .services.orchestrator import ProcessLookupOrchestrator, provider_capabilities
from .connectors.tribunal_registry import ALL_TRIBUNALS, FEDERAL_TRIBUNALS, DEFAULT_PRECAT_TRIBUNALS
from .services.official_precatorio_sources import official_precatorio_sources, official_precatorio_sources_summary, build_precatorio_route_plan
from .models import SearchLog, ProcessResult

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title='Claude Buscador de Processos', version='0.1.0', lifespan=lifespan)

# CORS: só libera cross-origin para as origens explicitamente listadas em
# FRONTEND_ALLOWED_ORIGINS. Nunca usa "*". Se a variável estiver vazia,
# nenhuma origem cross-origin é liberada (o painel embutido continua
# funcionando normalmente, pois é same-origin e não passa por CORS).
app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_allowed_origins(settings.frontend_allowed_origins),
    allow_methods=['GET', 'POST'],
    allow_headers=['Content-Type', 'X-Internal-Token'],
    allow_credentials=False,
)

app.mount('/static', StaticFiles(directory='app/static'), name='static')
templates = Jinja2Templates(directory='app/templates')


def _has_valid_session(request: Request) -> bool:
    if not settings.app_login_password:
        return False
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    return verify_session_token(cookie, settings.app_secret)


def verify_internal_token(request: Request, x_internal_token: str | None = Header(default=None)):
    """Protege as rotas /api/*.

    Aceita QUALQUER um dos dois, quando configurados:
    - header X-Internal-Token == INTERNAL_API_TOKEN (uso por script/CLI/curl);
    - sessão de login válida (cookie), para quem já entrou pela tela com APP_LOGIN_PASSWORD.

    Se nenhum dos dois estiver configurado, mantém o comportamento original: acesso aberto.
    """
    if not settings.internal_api_token and not settings.app_login_password:
        return
    if settings.internal_api_token and hmac.compare_digest(x_internal_token or '', settings.internal_api_token):
        return
    if _has_valid_session(request):
        return
    raise HTTPException(status_code=401, detail='Não autorizado. Faça login na tela ou informe X-Internal-Token.')


@app.get('/', response_class=HTMLResponse)
def index(request: Request):
    if settings.app_login_password and not _has_valid_session(request):
        return RedirectResponse(url='/login', status_code=303)
    return templates.TemplateResponse(request, 'index.html', {
        'all_tribunals': ALL_TRIBUNALS,
        'federal_tribunals': FEDERAL_TRIBUNALS,
        'default_precat_tribunals': DEFAULT_PRECAT_TRIBUNALS,
        'login_enabled': bool(settings.app_login_password),
    })


@app.get('/login', response_class=HTMLResponse)
def login_form(request: Request):
    if not settings.app_login_password or _has_valid_session(request):
        return RedirectResponse(url='/', status_code=303)
    return templates.TemplateResponse(request, 'login.html', {'error': None})


# Rate limit simples de tentativas de login: em memória, por IP. Suficiente
# pra uma ferramenta interna com um único usuário/senha compartilhada — não
# substitui um WAF de verdade, mas impede força bruta trivial via script.
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 15 * 60
_login_attempts: dict[str, list[float]] = {}


def _login_rate_limited(client_ip: str) -> bool:
    now = time.time()
    attempts = [t for t in _login_attempts.get(client_ip, []) if now - t < LOGIN_WINDOW_SECONDS]
    _login_attempts[client_ip] = attempts
    return len(attempts) >= LOGIN_MAX_ATTEMPTS


def _register_login_failure(client_ip: str) -> None:
    _login_attempts.setdefault(client_ip, []).append(time.time())


@app.post('/login', response_class=HTMLResponse)
def login_submit(request: Request, password: str = Form(...)):
    if not settings.app_login_password:
        return RedirectResponse(url='/', status_code=303)

    client_ip = request.client.host if request.client else 'unknown'
    if _login_rate_limited(client_ip):
        return templates.TemplateResponse(
            request,
            'login.html',
            {'error': f'Muitas tentativas. Aguarde {LOGIN_WINDOW_SECONDS // 60} minutos e tente de novo.'},
            status_code=429,
        )

    # Comparação constant-time: evita que diferenças no tempo de resposta
    # revelem quantos caracteres da senha estão certos (ataque de timing).
    if not hmac.compare_digest(password, settings.app_login_password):
        _register_login_failure(client_ip)
        return templates.TemplateResponse(
            request,
            'login.html',
            {'error': 'Senha incorreta.'},
            status_code=401,
        )
    token_ttl_seconds = 60 * 60 * 24 * max(1, settings.session_ttl_days)
    token = create_session_token(settings.app_secret, ttl_seconds=token_ttl_seconds)
    response = RedirectResponse(url='/', status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite='lax',
        secure=settings.app_env != 'local',
        max_age=token_ttl_seconds,
    )
    return response


@app.get('/logout')
def logout():
    response = RedirectResponse(url='/login', status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/api/tribunals', dependencies=[Depends(verify_internal_token)])
def tribunals():
    return {'all': ALL_TRIBUNALS, 'federal': FEDERAL_TRIBUNALS, 'default_precatorio': DEFAULT_PRECAT_TRIBUNALS}


@app.get('/api/capabilities', dependencies=[Depends(verify_internal_token)])
def capabilities():
    return {
        'message': 'Cada provedor/API declara os identificadores aceitos e campos extras que pode exigir.',
        'providers': provider_capabilities(),
    }


@app.post('/api/search', response_model=SearchResponse, dependencies=[Depends(verify_internal_token)])
async def search(request: SearchRequest, db: Session = Depends(get_db)):
    orchestrator = ProcessLookupOrchestrator(db)
    return await orchestrator.search(request)



@app.get('/api/official-precatorio/sources', dependencies=[Depends(verify_internal_token)])
def official_precatorio_source_registry():
    return {
        'message': 'Registro de fontes oficiais/institucionais para precatórios, RPVs, LOA, orçamento, fila e pagamento.',
        'summary': official_precatorio_sources_summary(),
        'sources': official_precatorio_sources(),
    }


@app.post('/api/official-precatorio/plan', dependencies=[Depends(verify_internal_token)])
def official_precatorio_plan(request: OfficialPrecatorioPlanRequest):
    search_type, search_key = request.resolved_type_and_key()
    return build_precatorio_route_plan(search_type, search_key, request.extra_params)


@app.post('/api/dossier', dependencies=[Depends(verify_internal_token)])
async def dossier(request: DossierRequest, db: Session = Depends(get_db)):
    """Monta a primeira versão do Dossiê/Raio-X.

    Nesta versão, o dossiê combina a busca processual já existente com o plano
    oficial de precatório/LOA. As fontes oficiais ainda aparecem como camadas
    de integração com status e campos exigidos, para impedir que a interface
    confunda indício processual DataJud com confirmação oficial de orçamento.
    """
    search_type, search_key = request.resolved_type_and_key()
    orchestrator = ProcessLookupOrchestrator(db)
    process_response = await orchestrator.search(request)
    official_plan = build_precatorio_route_plan(search_type, search_key, request.extra_params)
    return {
        'status': 'completed',
        'search_type': search_type,
        'search_key_masked': process_response.search_key_masked,
        'summary': {
            'process_results': process_response.total,
            'official_precatorio_sources_considered': len(official_plan['candidate_sources']),
            'missing_recommended_fields': official_plan['missing_recommended_fields'],
        },
        'processual_datajud_private_apis': process_response.model_dump(mode='json'),
        'official_precatorio_loa_budget_plan': official_plan,
        'important_note': 'Indício processual não confirma inscrição em LOA. Confirmação exige fonte oficial de precatório/LOA no plano.',
    }

@app.post('/api/official-precatorio/browser-search', dependencies=[Depends(verify_internal_token)])
async def official_precatorio_browser_search(request: BrowserSearchRequest):
    """Consulta um portal oficial via automação de navegador (Playwright).

    Hoje todos os conectores registrados aqui são stubs (ver
    app/services/portal_automation.py) — nenhum executa Playwright de
    verdade ainda, porque isso não pôde ser validado com acesso real ao
    site. A resposta é honesta: status 'not_implemented' com a explicação,
    nunca um dado inventado.
    """
    connector = PORTAL_AUTOMATION_STUBS.get(request.source_id)
    if not connector:
        raise HTTPException(
            status_code=404,
            detail=f'source_id desconhecido: {request.source_id}. Disponíveis: {", ".join(sorted(PORTAL_AUTOMATION_STUBS))}',
        )
    try:
        query = connector.build_query(request.search_type, request.search_key, request.extra_params)
        page = await connector.run_browser_search(query)
        blocker = connector.detect_blockers(page)
        if blocker:
            return {'status': blocker, 'source_id': connector.source_id, 'fonte_url': connector.fonte_url}
        raw = connector.extract_results(page)
        return connector.normalize_results(raw)
    except NotImplementedError:
        return connector.not_implemented_result().as_dict()


CHROME_EXECUTABLE_PATH = settings.playwright_chrome_path or None


@app.post('/api/portal-automation/start', dependencies=[Depends(verify_internal_token)])
async def portal_automation_start(request: PortalAutomationStartRequest):
    """Abre uma sessão de navegador real (Playwright), navega até a URL,
    preenche os campos informados. Se a página tiver captcha clássico
    (imagem + campo de texto), PARA e devolve a imagem pra você resolver —
    nunca resolve sozinho. Se não tiver captcha, segue e devolve o resultado
    direto. Se for reCAPTCHA/hCaptcha, avisa que este mecanismo não serve
    pra esse tipo (não dá pra "digitar" um desafio comportamental).

    Mecanismo genérico — funciona para qualquer URL/seletores que você
    informar, não só para os 8 stubs de app/services/portal_automation.py.
    """
    return await captcha_relay.start_browser_session(
        request.source_id, request.url, request.fill_fields, request.submit_selector,
        chrome_executable_path=CHROME_EXECUTABLE_PATH,
    )


@app.post('/api/portal-automation/{session_id}/solve', dependencies=[Depends(verify_internal_token)])
async def portal_automation_solve(session_id: str, request: PortalAutomationSolveRequest):
    """Retoma uma sessão pausada num captcha: você resolveu, manda o texto
    aqui, a automação digita e submete. A sessão expira em 5 minutos se
    ninguém resolver — depois disso, é preciso recomeçar a consulta."""
    return await captcha_relay.solve_captcha_session(session_id, request.captcha_text)


@app.post('/api/stj-precatorios/upload-xlsx', dependencies=[Depends(verify_internal_token)])
async def stj_upload_xlsx(file: UploadFile = File(...)):
    """Recebe o XLSX oficial do STJ baixado manualmente (processo/precatorios
    em stj.jus.br), salva em pasta local controlada (STJ_UPLOAD_DIR) e
    devolve um raio-x do arquivo: abas, cabeçalho encontrado, campos
    detectados e quantas linhas foram lidas. Não faz busca ainda — isso é
    o endpoint /api/stj-precatorios/search, separado.
    """
    content = await file.read()
    try:
        info = stj_uploads.save_uploaded_file(file.filename or 'arquivo.xlsx', content)
    except stj_uploads.InvalidUpload as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        inspection = stj_uploads.inspect_workbook(content, file.filename or '')
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f'Arquivo salvo, mas não consegui ler como XLSX/XLSM: {exc}')

    return {
        'status': 'uploaded',
        'arquivo_original': info.original_filename,
        'arquivo_salvo': info.stored_filename,
        'uploaded_at': info.uploaded_at,
        **inspection,
    }


@app.post('/api/stj-precatorios/search', dependencies=[Depends(verify_internal_token)])
def stj_search(request: StjSearchRequest):
    """Busca nos arquivos oficiais do STJ que já foram enviados via
    /api/stj-precatorios/upload-xlsx. Nunca cai para dado sintético: se
    nenhum arquivo foi carregado ainda, devolve status 'not_loaded' com a
    mensagem 'Arquivo oficial do STJ ainda não carregado.'
    """
    return stj_uploads.search_uploaded_files(request.search_type, request.search_key, request.ano_orcamento)


@app.get('/api/sources', dependencies=[Depends(verify_internal_token)])
def all_sources():
    """Visão única de tudo: precatório oficial + certidões + APIs
    processuais/comerciais externas. Não esconde nada não implementado —
    só separa por status real."""
    return {
        'message': 'Mapa mestre de fontes/APIs. Ver docs/API_DISCOVERY_MASTER.md para o levantamento completo com fontes pesquisadas.',
        'summary': source_master.master_sources_summary(),
        'precatorio_oficial': official_precatorio_sources(),
        'certidoes': certificate_center.certificate_sources(),
        'externo_comercial': source_master.external_sources(),
    }


@app.get('/api/certificates/sources', dependencies=[Depends(verify_internal_token)])
def certificate_sources_endpoint():
    return {
        'message': 'Fontes de certidões (certificate_center). Status honesto por fonte — nenhuma certidão é inventada.',
        'sources': certificate_center.certificate_sources(),
    }


@app.post('/api/certificates/plan', dependencies=[Depends(verify_internal_token)])
def certificate_plan(request: CertificatePlanRequest):
    return certificate_center.build_certificate_plan(request.document, request.certificate_types)


@app.post('/api/certificates/request', dependencies=[Depends(verify_internal_token)])
async def certificate_request(request: CertificateRequestInput, db: Session = Depends(get_db)):
    result = await certificate_center.request_certificate(
        request.source_id, request.certificate_type, request.document, request.name, request.extra,
    )
    from .utils.cpf import mask_document
    record = CertificateRecord(
        source_id=request.source_id,
        certificate_type=request.certificate_type,
        document_masked=mask_document(request.document) if request.document else None,
        name_consulted=request.name,
        status=result.get('status', 'erro'),
        message=result.get('message'),
        validation_code=result.get('validation_code'),
        pdf_path=result.get('pdf_path'),
        fonte_url=result.get('fonte_url'),
        issued_at=result.get('issued_at'),
        valid_until=result.get('valid_until'),
        raw=result.get('raw'),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {'id': record.id, 'created_at': record.created_at.isoformat(), **result}


@app.get('/api/certificates/{certificate_id}', dependencies=[Depends(verify_internal_token)])
def certificate_get(certificate_id: int, db: Session = Depends(get_db)):
    record = db.query(CertificateRecord).filter(CertificateRecord.id == certificate_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f'Certidão {certificate_id} não encontrada.')
    return {
        'id': record.id,
        'created_at': record.created_at.isoformat(),
        'source_id': record.source_id,
        'certificate_type': record.certificate_type,
        'document_masked': record.document_masked,
        'name_consulted': record.name_consulted,
        'status': record.status,
        'message': record.message,
        'validation_code': record.validation_code,
        'pdf_path': record.pdf_path,
        'fonte_url': record.fonte_url,
        'issued_at': record.issued_at,
        'valid_until': record.valid_until,
        'raw': record.raw,
    }


@app.post('/api/evidencias', dependencies=[Depends(verify_internal_token)])
async def registrar_evidencia_manual(
    fonte: str = Form(...),
    referencia: str = Form(''),
    texto: str = Form(''),
    arquivo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    """Registro manual de evidência: quando uma fonte ainda não é
    automatizada, o usuário pode colar o texto que encontrou e/ou anexar
    um arquivo (PDF/XLSX/print), e isso fica guardado — nunca inventado."""
    arquivo_nome = None
    arquivo_caminho = None
    if arquivo is not None and arquivo.filename:
        content = await arquivo.read()
        try:
            arquivo_nome, arquivo_caminho = manual_evidence.save_evidence_file(arquivo.filename, content)
        except manual_evidence.InvalidEvidenceFile as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    if not texto.strip() and not arquivo_nome:
        raise HTTPException(status_code=400, detail='Informe o texto encontrado ou anexe um arquivo — não dá pra salvar uma evidência vazia.')

    registro = ManualEvidence(
        fonte=fonte,
        referencia=referencia or None,
        texto=texto or None,
        arquivo_nome=arquivo_nome,
        arquivo_caminho=arquivo_caminho,
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return {
        'id': registro.id,
        'created_at': registro.created_at.isoformat(),
        'fonte': registro.fonte,
        'referencia': registro.referencia,
        'tem_texto': bool(registro.texto),
        'arquivo_nome': registro.arquivo_nome,
        'status': 'salvo',
    }


@app.get('/api/evidencias', dependencies=[Depends(verify_internal_token)])
def listar_evidencias_manuais(referencia: str | None = None, limit: int = 50, db: Session = Depends(get_db)):
    query = db.query(ManualEvidence).order_by(ManualEvidence.created_at.desc())
    if referencia:
        query = query.filter(ManualEvidence.referencia == referencia)
    registros = query.limit(limit).all()
    return [{
        'id': r.id,
        'created_at': r.created_at.isoformat(),
        'fonte': r.fonte,
        'referencia': r.referencia,
        'texto': r.texto,
        'arquivo_nome': r.arquivo_nome,
    } for r in registros]


@app.get('/api/history', dependencies=[Depends(verify_internal_token)])
def history(limit: int = 50, db: Session = Depends(get_db)):
    logs = db.query(SearchLog).order_by(SearchLog.created_at.desc()).limit(limit).all()
    return [{
        'id': row.id,
        'created_at': row.created_at.isoformat(),
        'provider': row.provider,
        'search_type': row.search_type,
        'search_key_masked': row.search_key_masked,
        'tribunals': row.tribunals,
        'status': row.status,
        'notes': row.notes,
    } for row in logs]


@app.get('/api/results/{search_log_id}', dependencies=[Depends(verify_internal_token)])
def results(search_log_id: int, db: Session = Depends(get_db)):
    rows = db.query(ProcessResult).filter(ProcessResult.search_log_id == search_log_id).order_by(ProcessResult.precatorio_score.desc()).all()
    return [{
        'provider': r.provider,
        'tribunal': r.tribunal,
        'numero_processo': r.numero_processo,
        'classe': r.classe,
        'assunto': r.assunto,
        'orgao_julgador': r.orgao_julgador,
        'data_ajuizamento': r.data_ajuizamento,
        'ultima_atualizacao': r.ultima_atualizacao,
        'precatorio_score': r.precatorio_score,
        'precatorio_flags': r.precatorio_flags,
    } for r in rows]
