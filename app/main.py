from __future__ import annotations

import hmac
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .auth import SESSION_COOKIE_NAME, create_session_token, verify_session_token
from .config import get_settings, parse_allowed_origins
from .db import get_db, init_db
from .schemas import SearchRequest, SearchResponse, OfficialPrecatorioPlanRequest, DossierRequest, BrowserSearchRequest, StjSearchRequest, CertificatePlanRequest, CertificateRequestInput, PortalAutomationStartRequest, PortalAutomationSolveRequest, DiligenciaRequest, BotsRunRequest, BotsResumeRequest, IntakeWhatsappManualRequest
from .services import stj_uploads
from .services import certificate_center
from .services import source_master
from .services import captcha_relay
from .services import diligencia_engine
from .services import whatsapp_intake
from .bots import runner as bots_runner
from .bots import intake_bot
from .bots.portal_bot import PortalBot
from .services import manual_evidence
from .models import CertificateRecord, ManualEvidence, DiligenciaLog, BotJob, BotStep, Lead, WhatsAppMessage, IntakeCase, WatcherRun, PublicationHit, OpportunityLead
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
        # Achado real da auditoria: em produção sem senha, a ferramenta fica
        # aberta pra qualquer um com o link. Isso avisa na própria tela,
        # visível toda vez, em vez de só um log que ninguém vê.
        'alerta_producao_sem_senha': settings.app_env not in ('local', 'development', 'dev', 'test') and not settings.app_login_password,
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


@app.get('/api/diagnostico', dependencies=[Depends(verify_internal_token)])
def diagnostico_sistema():
    """Diagnóstico honesto do que está configurado agora — pra responder,
    sem jargão, a pergunta 'minha ferramenta está pronta pra quê?'."""
    from .config import datajud_key_source
    stj_dir = stj_uploads.upload_dir()
    stj_arquivos = list(stj_dir.glob('*.xls*')) if stj_dir.exists() else []
    ev_dir = manual_evidence.evidence_dir()
    ev_arquivos = list(ev_dir.glob('*')) if ev_dir.exists() else []

    return {
        'datajud': {
            'ativo': True,
            'chave': 'chave pública padrão do CNJ' if datajud_key_source() == 'chave_publica_padrao' else 'chave própria configurada',
            'cobre': 'Consulta por CNJ/número de processo (não busca por CPF/nome).',
        },
        'judit': {
            'ativo': bool(settings.judit_enabled and settings.judit_api_key),
            'cobre': 'Busca por CPF, CNPJ, nome e OAB.',
            'proxima_acao': None if (settings.judit_enabled and settings.judit_api_key) else 'Não configurada. Busca por nome funciona de graça dentro dos dados do STJ já carregados.',
        },
        'stj': {
            'arquivo_carregado': len(stj_arquivos) > 0,
            'quantidade_arquivos': len(stj_arquivos),
            'pasta_em_uso': str(stj_dir),
        },
        'serpro_cnd': {
            'ativo': bool(settings.serpro_cnd_consumer_key and settings.serpro_cnd_consumer_secret),
            'cobre': 'Certidão de Regularidade Fiscal (Receita/PGFN) automática.',
        },
        'evidencias_manuais': {
            'pasta_em_uso': str(ev_dir),
            'quantidade_salva': len(ev_arquivos),
        },
        'login': {
            'ativo': bool(settings.app_login_password),
            'sessao_dura_dias': settings.session_ttl_days,
        },
        'banco_de_dados': {
            'url': settings.database_url,
            'persistente': '/data' in settings.database_url or not settings.database_url.startswith('sqlite:///./'),
        },
    }


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
def official_precatorio_plan(request: OfficialPrecatorioPlanRequest, db: Session = Depends(get_db)):
    search_type, search_key = request.resolved_type_and_key()
    plano = build_precatorio_route_plan(search_type, search_key, request.extra_params)

    candidatos = plano.get('candidate_sources') or []
    faltando = plano.get('missing_recommended_fields') or []
    from .services.official_precatorio_sources import classificar_prontas_e_proxima_acao
    prontas, proxima_acao, pendencias_stj = classificar_prontas_e_proxima_acao(candidatos, faltando)

    log = _salvar_diligencia(
        db, input_original=search_key, tipo_identificado=search_type, valor_normalizado=search_key,
        objetivo='precatorio', resumo_humano=f'{len(candidatos)} fonte(s) candidata(s) mapeada(s) no plano.',
        proxima_acao_recomendada=proxima_acao,
        pendencias=[f'Informe {c} para restringir melhor o plano.' for c in faltando] + pendencias_stj,
        fontes_manuais_recomendadas=[{'fonte': c.get('name'), 'acao': 'Abrir link oficial'} for c in candidatos if c.get('official_url')],
        raw_avancado=plano,
    )
    plano['diligencia_id'] = log.id
    return plano


@app.post('/api/diligencia', dependencies=[Depends(verify_internal_token)])
async def diligencia(request: DiligenciaRequest, db: Session = Depends(get_db)):
    """Motor Operacional de Diligência (v28/v29): ponto único de entrada — recebe
    qualquer dado digitado (CPF, CNPJ, nome, OAB, CNJ, sequencial STJ,
    precatório/RPV/requisitório) e devolve uma resposta humana e
    estruturada, orquestrando os serviços já existentes (DataJud, STJ XLSX,
    planejador de precatório, certidões). Funciona independente da tela —
    qualquer cliente (a tela, um script, outra IA) pode chamar isto direto.
    Cada chamada fica salva (DiligenciaLog) — dá pra reabrir depois em
    /api/diligencias/{id} ou como dossiê em /api/diligencias/{id}/dossie."""
    resultado = await diligencia_engine.run_diligencia(
        input_texto=request.input,
        uf=request.uf,
        tribunal=request.tribunal,
        objetivo=request.objetivo,
    )
    log = DiligenciaLog(
        input_original=request.input,
        tipo_identificado=resultado['tipo_identificado'],
        valor_normalizado=resultado['valor_normalizado'],
        objetivo=request.objetivo,
        status='completed',
        resumo_humano=resultado.get('resumo_humano'),
        proxima_acao_recomendada=resultado.get('proxima_acao_recomendada'),
        resultados_confirmados=resultado.get('resultados_confirmados'),
        indicios=resultado.get('indicios'),
        pendencias=resultado.get('pendencias'),
        fontes_manuais_recomendadas=resultado.get('fontes_manuais_recomendadas'),
        raw_avancado=resultado.get('raw_avancado'),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    resultado['diligencia_id'] = log.id

    if request.run_bots:
        bots_resultado = await bots_runner.executar_bots(request.input, request.uf, request.tribunal, request.objetivo, db=db)
        job = BotJob(
            input_original=request.input, tipo_identificado=bots_resultado['tipo_identificado'],
            objetivo=request.objetivo, status=bots_resultado['status'],
            resumo_humano=bots_resultado['resumo_humano'], proxima_acao=bots_resultado['proxima_acao_recomendada'],
            raw=bots_resultado,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        for passo in bots_resultado['bots_executados']:
            evidence_ids = passo.get('evidence_ids') or []
            db.add(BotStep(
                job_id=job.id, bot_name=passo['bot_id'], status=passo['status'],
                finished_at=datetime.now(timezone.utc) if passo['status'] != 'waiting_user' else None,
                resultado=passo.get('resultado'), warning='; '.join(passo.get('warnings') or []) or None,
                next_action=passo.get('next_action'), evidence_id=evidence_ids[0] if evidence_ids else None,
            ))
        db.commit()
        resultado['job_id'] = job.id
        resultado['bots_resumo'] = {
            'status': bots_resultado['status'],
            'bots_executados': [{'bot_id': b['bot_id'], 'nome': b['nome'], 'status': b['status']} for b in bots_resultado['bots_executados']],
        }

    return resultado


@app.get('/api/diligencias', dependencies=[Depends(verify_internal_token)])
def listar_diligencias(limit: int = 50, db: Session = Depends(get_db)):
    """Lista as últimas diligências salvas, mais recente primeiro."""
    logs = db.query(DiligenciaLog).order_by(DiligenciaLog.created_at.desc()).limit(limit).all()
    return [{
        'id': l.id,
        'created_at': l.created_at.isoformat(),
        'input_original': l.input_original,
        'tipo_identificado': l.tipo_identificado,
        'valor_normalizado': l.valor_normalizado,
        'resumo_humano': l.resumo_humano,
        'proxima_acao_recomendada': l.proxima_acao_recomendada,
    } for l in logs]


def _diligencia_ou_404(diligencia_id: int, db: Session) -> DiligenciaLog:
    log = db.query(DiligenciaLog).filter(DiligenciaLog.id == diligencia_id).first()
    if not log:
        raise HTTPException(status_code=404, detail=f'Diligência {diligencia_id} não encontrada.')
    return log


def _salvar_diligencia(
    db: Session, *, input_original: str, tipo_identificado: str, valor_normalizado: str,
    objetivo: str, resumo_humano: str | None = None, proxima_acao_recomendada: str | None = None,
    resultados_confirmados: list | None = None, indicios: list | None = None,
    pendencias: list | None = None, fontes_manuais_recomendadas: list | None = None,
    raw_avancado: dict | None = None,
) -> DiligenciaLog:
    """Ponto único de gravação de DiligenciaLog — usado tanto pelo motor
    (/api/diligencia) quanto pelos fluxos dedicados (STJ, precatório,
    certidões), pra que TODA consulta feita na ferramenta fique salva e
    reabrível como dossiê, não só a busca livre."""
    log = DiligenciaLog(
        input_original=input_original[:500],
        tipo_identificado=tipo_identificado,
        valor_normalizado=valor_normalizado[:500],
        objetivo=objetivo,
        status='completed',
        resumo_humano=resumo_humano,
        proxima_acao_recomendada=proxima_acao_recomendada,
        resultados_confirmados=resultados_confirmados,
        indicios=indicios,
        pendencias=pendencias,
        fontes_manuais_recomendadas=fontes_manuais_recomendadas,
        raw_avancado=raw_avancado,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@app.get('/api/diligencias/{diligencia_id}', dependencies=[Depends(verify_internal_token)])
def obter_diligencia(diligencia_id: int, db: Session = Depends(get_db)):
    """Reabre uma diligência salva, com todo o detalhe (não só o resumo)."""
    log = _diligencia_ou_404(diligencia_id, db)
    return {
        'id': log.id,
        'created_at': log.created_at.isoformat(),
        'input_original': log.input_original,
        'tipo_identificado': log.tipo_identificado,
        'valor_normalizado': log.valor_normalizado,
        'objetivo': log.objetivo,
        'status': log.status,
        'resumo_humano': log.resumo_humano,
        'proxima_acao_recomendada': log.proxima_acao_recomendada,
        'resultados_confirmados': log.resultados_confirmados,
        'indicios': log.indicios,
        'pendencias': log.pendencias,
        'fontes_manuais_recomendadas': log.fontes_manuais_recomendadas,
        'raw_avancado': log.raw_avancado,
    }


@app.get('/api/diligencias/{diligencia_id}/dossie', response_class=HTMLResponse)
def dossie_diligencia(diligencia_id: int, request: Request, db: Session = Depends(get_db)):
    """Página HTML simples e imprimível do dossiê de uma diligência salva."""
    if settings.app_login_password and not _has_valid_session(request):
        return RedirectResponse(url='/login', status_code=303)
    log = _diligencia_ou_404(diligencia_id, db)
    return templates.TemplateResponse(request, 'dossie.html', {'log': log})


@app.post('/api/bots/run', dependencies=[Depends(verify_internal_token)])
async def bots_run(request: BotsRunRequest, db: Session = Depends(get_db)):
    """Camada de bots executores (v30): mesma identificação de dado do
    motor (/api/diligencia), mas com rastreamento por bot/etapa (BotJob +
    BotStep) — cada bot que rodou, o que encontrou, o que falhou, o que
    ficou pendente. Se um bot pausar esperando validação humana (ex.:
    PortalBot num captcha), o job fica com status 'waiting_user' e pode ser
    retomado em POST /api/bots/jobs/{id}/resume."""
    resultado = await bots_runner.executar_bots(request.input, request.uf, request.tribunal, request.objetivo, db=db)

    if request.portal_url and request.portal_fill_fields and request.portal_submit_selector:
        portal_result = await PortalBot().run_com_alvo(
            request.portal_source_id or 'portal_manual', request.portal_url,
            request.portal_fill_fields, request.portal_submit_selector,
        )
        resultado['bots_executados'].append(portal_result.as_dict())
        if portal_result.status == 'waiting_user':
            resultado['status'] = 'waiting_user'
            resultado['proxima_acao_recomendada'] = portal_result.next_action
        resultado['pendencias'] += portal_result.pendencias

    job = BotJob(
        input_original=request.input, tipo_identificado=resultado['tipo_identificado'],
        objetivo=request.objetivo, status=resultado['status'],
        resumo_humano=resultado['resumo_humano'], proxima_acao=resultado['proxima_acao_recomendada'],
        raw=resultado,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    for passo in resultado['bots_executados']:
        evidence_ids = passo.get('evidence_ids') or []
        db.add(BotStep(
            job_id=job.id, bot_name=passo['bot_id'], status=passo['status'],
            finished_at=datetime.now(timezone.utc) if passo['status'] != 'waiting_user' else None,
            resultado=passo.get('resultado'),
            warning='; '.join(passo.get('warnings') or []) or None,
            next_action=passo.get('next_action'),
            evidence_id=evidence_ids[0] if evidence_ids else None,
        ))
    db.commit()

    resultado['job_id'] = job.id
    return resultado


@app.get('/api/bots/jobs', dependencies=[Depends(verify_internal_token)])
def bots_jobs_list(limit: int = 50, db: Session = Depends(get_db)):
    jobs = db.query(BotJob).order_by(BotJob.created_at.desc()).limit(limit).all()
    return [{
        'id': j.id, 'created_at': j.created_at.isoformat(), 'input_original': j.input_original,
        'tipo_identificado': j.tipo_identificado, 'status': j.status,
        'resumo_humano': j.resumo_humano, 'proxima_acao': j.proxima_acao,
    } for j in jobs]


@app.get('/api/bots/jobs/{job_id}', dependencies=[Depends(verify_internal_token)])
def bots_job_detail(job_id: int, db: Session = Depends(get_db)):
    job = db.query(BotJob).filter(BotJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f'Job {job_id} não encontrado.')
    steps = db.query(BotStep).filter(BotStep.job_id == job_id).all()
    return {
        'id': job.id, 'created_at': job.created_at.isoformat(), 'updated_at': job.updated_at.isoformat(),
        'input_original': job.input_original, 'tipo_identificado': job.tipo_identificado,
        'objetivo': job.objetivo, 'status': job.status, 'resumo_humano': job.resumo_humano,
        'proxima_acao': job.proxima_acao, 'raw': job.raw,
        'steps': [{
            'id': s.id, 'bot_name': s.bot_name, 'status': s.status,
            'started_at': s.started_at.isoformat(), 'finished_at': s.finished_at.isoformat() if s.finished_at else None,
            'resultado': s.resultado, 'warning': s.warning, 'erro': s.erro, 'next_action': s.next_action,
            'evidence_id': s.evidence_id,
        } for s in steps],
    }


@app.post('/api/bots/jobs/{job_id}/resume', dependencies=[Depends(verify_internal_token)])
async def bots_job_resume(job_id: int, request: BotsResumeRequest, db: Session = Depends(get_db)):
    """Retoma um job pausado num captcha (PortalBot). Recebe o texto que o
    humano leu na imagem, digita e submete — nunca resolve o captcha
    sozinho."""
    job = db.query(BotJob).filter(BotJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f'Job {job_id} não encontrado.')
    if job.status != 'waiting_user':
        raise HTTPException(status_code=400, detail=f'Job {job_id} não está aguardando intervenção (status atual: {job.status}).')

    step_pausado = db.query(BotStep).filter(BotStep.job_id == job_id, BotStep.status == 'waiting_user').first()
    if not step_pausado or not (step_pausado.resultado or {}).get('session_id'):
        raise HTTPException(status_code=400, detail='Não achei a sessão de navegador pausada pra este job.')

    session_id = step_pausado.resultado['session_id']
    bot_result = await PortalBot().resume(session_id, request.captcha_text)

    step_pausado.status = bot_result.status
    step_pausado.finished_at = datetime.now(timezone.utc)
    step_pausado.resultado = bot_result.resultado
    step_pausado.next_action = bot_result.next_action
    job.status = 'completed' if bot_result.status == 'concluido' else 'partial'
    job.proxima_acao = bot_result.next_action
    db.commit()

    return bot_result.as_dict()


@app.get('/api/bots/status', dependencies=[Depends(verify_internal_token)])
def bots_status_endpoint():
    """Lista os bots que existem e o que cada um faz de verdade hoje."""
    return {'bots': bots_runner.bots_status()}


def _obter_ou_criar_lead(db: Session, telefone: str | None, dados: dict) -> Lead:
    lead = None
    if telefone:
        lead = db.query(Lead).filter(Lead.telefone == telefone).order_by(Lead.id.desc()).first()
    if not lead:
        lead = Lead(
            telefone=telefone, nome=dados.get('nome'), cpf=dados.get('cpf'), cnpj=dados.get('cnpj'),
            origem='whatsapp_manual',
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
    elif dados.get('nome') and not lead.nome:
        lead.nome = dados['nome']
        db.commit()
    return lead


@app.post('/api/intake/whatsapp/manual', dependencies=[Depends(verify_internal_token)])
async def intake_whatsapp_manual(request: IntakeWhatsappManualRequest, db: Session = Depends(get_db)):
    """v31 — IntakeBot manual: recebe texto colado do WhatsApp, extrai
    CPF/CNJ/nome/UF/ente devedor, normaliza o CNJ, infere tribunal, aponta
    divergência, aciona os bots existentes quando há processo detectado,
    salva a mensagem original como evidência e gera dossiê."""
    dados = whatsapp_intake.processar_mensagem(request.texto)
    resposta_sugerida = whatsapp_intake.gerar_resposta_sugerida(dados)

    lead = _obter_ou_criar_lead(db, request.telefone, dados)

    msg = WhatsAppMessage(lead_id=lead.id, telefone=request.telefone, texto_original=request.texto, raw=dados)
    db.add(msg)
    db.commit()

    from .bots.evidence_bot import registrar_evidencia_automatica
    evidence_id = registrar_evidencia_automatica(
        fonte='WhatsApp (mensagem colada manualmente)',
        referencia=dados['processos_detectados'][0]['cnj_normalizado'] if dados['processos_detectados'] else (request.telefone or 'sem-referencia'),
        texto=request.texto,
    )

    job_id = None
    if dados['processos_detectados']:
        bots_resultado = await intake_bot.acionar_bots_para_caso(dados, db=db)
        if bots_resultado:
            bots_resultado['contexto_documento'] = {
                'classe_documento': dados.get('classe_documento'),
                'eh_requisitorio_ou_precatorio': dados.get('eh_requisitorio_ou_precatorio'),
                'valor_causa': dados.get('valor_causa'),
                'orgao_julgador': dados.get('orgao_julgador'),
                'processo_referencia': dados.get('processo_referencia'),
            }
            job = BotJob(
                input_original=dados['processos_detectados'][0]['cnj_normalizado'],
                tipo_identificado=bots_resultado['tipo_identificado'], objetivo='completo',
                status=bots_resultado['status'], resumo_humano=bots_resultado['resumo_humano'],
                proxima_acao=bots_resultado['proxima_acao_recomendada'], raw=bots_resultado,
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            for passo in bots_resultado['bots_executados']:
                evidence_ids = passo.get('evidence_ids') or []
                db.add(BotStep(
                    job_id=job.id, bot_name=passo['bot_id'], status=passo['status'],
                    finished_at=datetime.now(timezone.utc) if passo['status'] != 'waiting_user' else None,
                    resultado=passo.get('resultado'), warning='; '.join(passo.get('warnings') or []) or None,
                    next_action=passo.get('next_action'), evidence_id=evidence_ids[0] if evidence_ids else None,
                ))
            db.commit()
            job_id = job.id

    # v31f: se o documento cita um processo referência (ex.: ação
    # rescisória apontando pro processo original), consulta ele também —
    # não fica só no processo principal.
    job_id_referencia = None
    if dados.get('processo_referencia'):
        dados_ref = {'processos_detectados': [dados['processo_referencia']]}
        bots_resultado_ref = await intake_bot.acionar_bots_para_caso(dados_ref, db=db)
        if bots_resultado_ref:
            job_ref = BotJob(
                input_original=dados['processo_referencia']['cnj_normalizado'],
                tipo_identificado=bots_resultado_ref['tipo_identificado'], objetivo='completo',
                status=bots_resultado_ref['status'], resumo_humano='Processo referência citado no documento — ' + bots_resultado_ref['resumo_humano'],
                proxima_acao=bots_resultado_ref['proxima_acao_recomendada'], raw=bots_resultado_ref,
            )
            db.add(job_ref)
            db.commit()
            db.refresh(job_ref)
            for passo in bots_resultado_ref['bots_executados']:
                evidence_ids = passo.get('evidence_ids') or []
                db.add(BotStep(
                    job_id=job_ref.id, bot_name=passo['bot_id'], status=passo['status'],
                    finished_at=datetime.now(timezone.utc) if passo['status'] != 'waiting_user' else None,
                    resultado=passo.get('resultado'), warning='; '.join(passo.get('warnings') or []) or None,
                    next_action=passo.get('next_action'), evidence_id=evidence_ids[0] if evidence_ids else None,
                ))
            db.commit()
            job_id_referencia = job_ref.id

    # v31e/v31f: quando o DataJud não encontrou nada, mas o documento traz
    # contexto rico (classe, requisitório/precatório, processo referência),
    # a próxima ação deve usar esse contexto — nunca só "não encontrado",
    # e tem prioridade sobre o genérico "peça CPF/nome" (achado real: como
    # CPF/nome quase sempre faltam numa mensagem só com o número do
    # processo, o genérico sempre ganhava e a mensagem rica nunca aparecia).
    proxima_acao = dados['divergencias'][0] if dados['divergencias'] else None
    if not proxima_acao and job_id:
        job_criado = db.query(BotJob).filter(BotJob.id == job_id).first()
        # Achado real de auditoria: checar só job.status (partial/failed)
        # não capturava o caso "DataJud foi consultado com sucesso, mas
        # veio vazio" — esse caso deixa o step (e o job) como 'concluido',
        # não 'partial'. Documento com contexto forte (ofício requisitório,
        # ação rescisória, processo referência) precisa ganhar prioridade
        # sempre que o DataJud não confirmou nada, seja por falha OU por
        # retorno vazio — nunca só "peça CPF/nome".
        datajud_sem_resultado = False
        if job_criado:
            steps_datajud = [s for s in (bots_resultado.get('bots_executados') or []) if s['bot_id'] == 'datajud_bot']
            if steps_datajud:
                status_consulta = ((steps_datajud[0].get('resultado') or {}).get('consulta') or {}).get('status_consulta')
                sem_resultados_confirmados = not (steps_datajud[0].get('resultado') or {}).get('resultados_confirmados')
                datajud_sem_resultado = (
                    status_consulta in {'consultado_sem_resultado', 'falhou'}
                    or steps_datajud[0]['status'] == 'falhou'
                    or (steps_datajud[0]['status'] == 'concluido' and sem_resultados_confirmados)
                )
            else:
                datajud_sem_resultado = job_criado.status in {'partial', 'failed'}
        if datajud_sem_resultado and dados.get('classe_documento') == 'Ação Rescisória' and dados.get('processo_referencia'):
            tribunal = dados['processos_detectados'][0].get('tribunal_provavel') if dados['processos_detectados'] else None
            proxima_acao = (
                f"CNJ válido e tribunal inferido: {tribunal}. A consulta DataJud não retornou resultado para este número. "
                f"Como o documento indica ação rescisória e traz processo referência, consulte também o processo "
                f"referência {dados['processo_referencia']['cnj_normalizado']}."
            )
        elif datajud_sem_resultado and dados.get('eh_requisitorio_ou_precatorio') and dados['processos_detectados']:
            tribunal = dados['processos_detectados'][0].get('tribunal_provavel')
            sufixo = dados['processos_detectados'][0].get('sufixo')
            proxima_acao = (
                f'Consultamos o DataJud para o {tribunal} usando o CNJ base {dados["processos_detectados"][0]["cnj_normalizado"]}'
                + (f' (o sufixo /{sufixo} do documento indica incidente/desdobramento, não faz parte do CNJ em si)' if sufixo else '')
                + f', mas não houve retorno. Como o documento é um ofício requisitório/precatório, a fonte principal '
                + f'de confirmação deve ser o {tribunal}/DEPRE (órgão de precatórios do tribunal).'
            )
    if not proxima_acao and dados['dados_faltantes']:
        proxima_acao = f"Peça também: {', '.join(dados['dados_faltantes'])}"
    if not proxima_acao:
        proxima_acao = 'Bots acionados — confira o dossiê.'

    case = IntakeCase(
        lead_id=lead.id, input_original=request.texto, dados_extraidos=dados,
        processos_detectados=dados['processos_detectados'], divergencias=dados['divergencias'],
        dados_faltantes=dados['dados_faltantes'], resposta_sugerida=resposta_sugerida,
        job_id=job_id, job_id_referencia=job_id_referencia,
    )
    db.add(case)
    db.commit()
    db.refresh(case)

    return {
        'lead_id': lead.id,
        'case_id': case.id,
        'dados_extraidos': {
            **{k: v for k, v in dados.items() if k not in {'cpf', 'cnpj', 'texto_original'}},
            'texto_original': whatsapp_intake.mascarar_documentos_no_texto(dados['texto_original']),
        },
        'processos_detectados': dados['processos_detectados'],
        'processo_referencia': dados.get('processo_referencia'),
        'classe_documento': dados.get('classe_documento'),
        'eh_requisitorio_ou_precatorio': dados.get('eh_requisitorio_ou_precatorio'),
        'divergencias': dados['divergencias'],
        'dados_faltantes': dados['dados_faltantes'],
        'proxima_acao': proxima_acao,
        'resposta_sugerida': resposta_sugerida,
        'job_id': job_id,
        'job_id_referencia': job_id_referencia,
        'evidence_id': evidence_id,
    }


@app.post('/api/intake/whatsapp/screenshot', dependencies=[Depends(verify_internal_token)])
async def intake_whatsapp_screenshot(
    telefone: str = Form(''),
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """v31 — recebe print do WhatsApp. Sem OCR configurado (decisão
    deliberada, não uma falha): salva o print como evidência e pede o
    texto colado manualmente — nunca trava o fluxo."""
    from .services import manual_evidence
    content = await arquivo.read()
    try:
        arquivo_nome, arquivo_caminho = manual_evidence.save_evidence_file(arquivo.filename, content)
    except manual_evidence.InvalidEvidenceFile as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    lead = _obter_ou_criar_lead(db, telefone, {})
    msg = WhatsAppMessage(lead_id=lead.id, telefone=telefone, arquivo_evidencia=arquivo_caminho, raw={'ocr': 'nao_configurado'})
    db.add(msg)
    db.commit()
    db.refresh(msg)

    return {
        'lead_id': lead.id,
        'message_id': msg.id,
        'ocr_disponivel': False,
        'proxima_acao': 'OCR não configurado nesta versão. Cole abaixo o texto da conversa pra extrairmos os dados — o print já ficou salvo como evidência.',
        'evidencia_arquivo': arquivo.filename,
    }


@app.get('/api/datajud/diagnostico/{cnj}', dependencies=[Depends(verify_internal_token)])
async def datajud_diagnostico_endpoint(cnj: str, tribunal: str | None = None):
    """v31d — Auditoria multi-tribunal: mostra exatamente qual alias e
    endpoint do DataJud foram consultados pra este CNJ específico, o
    status HTTP, e se foi encontrado/vazio/erro/alias não configurado.
    Não é 'mais uma suposição' — chama o DataJud de verdade pro tribunal
    inferido (ou informado) e reporta o que aconteceu."""
    from .services.datajud_diagnostico import diagnosticar_cnj
    return await diagnosticar_cnj(cnj, tribunal)


@app.get('/api/watchers/status', dependencies=[Depends(verify_internal_token)])
def watchers_status():
    """v32.1 — o que existe hoje, e com que grau de automação real."""
    from .config import get_settings
    settings_local = get_settings()
    auto_run_bots = getattr(settings_local, 'watchers_auto_run_bots', False)
    return {
        'watchers': [
            {'name': 'publication_watcher', 'descricao': 'Classifica publicações fornecidas (fixture local ou fonte externa que você conectar) em sinais de oportunidade.', 'fonte': 'fixture_ou_externa'},
            {'name': 'datajud_movement_watcher', 'descricao': 'Revarre CNJs já conhecidos no DataJud, procurando movimentação nova compatível com sinal de interesse.', 'fonte': 'datajud_real'},
            {'name': 'stj_official_file_watcher', 'descricao': 'Roda o sync oficial do STJ (v30.2) e cria lead pra registro novo desde a última rodada.', 'fonte': 'stj_real'},
        ],
        'bots_automaticos': {
            'ativado': auto_run_bots,
            'descricao': 'Bots automáticos ' + ('ativados' if auto_run_bots else 'desativados') + ' — leads de prioridade alta ' + ('acionam bots sozinhos quando o watcher roda.' if auto_run_bots else 'precisam do botão "Rodar bots" (padrão, pra não sobrecarregar).'),
            'variavel_de_ambiente': 'WATCHERS_AUTO_RUN_BOTS',
        },
        'agendamento': {
            'cron_nativo_ativo': False,
            'motivo': 'Render Cron Job custa no mínimo US$ 1/mês — sem tier gratuito.',
            'alternativa_gratuita': 'Configure um cron externo gratuito (ex.: cron-job.org) fazendo POST diário em /api/watchers/run.',
            'endpoint': '/api/watchers/run', 'metodo': 'POST',
            'headers_necessarios': 'X-Internal-Token (se INTERNAL_API_TOKEN estiver configurado)',
            'horario_sugerido': '06:00 (antes do expediente)',
        },
    }


def _fixture_publicacoes_exemplo() -> list[dict]:
    """Fixture de demonstração — mostra a esteira completa funcionando
    sem depender de fonte externa (ver RELATORIO_V32 pra explicação
    honesta sobre acesso real ao DJEN). Vive dentro do próprio pacote da
    aplicação (não em tests/), garantindo que existe em produção também."""
    import json
    from pathlib import Path
    caminho = Path(__file__).parent / 'watchers' / 'sample_data' / 'publicacoes_exemplo.json'
    if caminho.exists():
        return json.loads(caminho.read_text(encoding='utf-8'))
    return []


@app.post('/api/watchers/run', dependencies=[Depends(verify_internal_token)])
async def watchers_run(request: Request, db: Session = Depends(get_db)):
    """v32 — aciona os watchers manualmente. Corpo opcional:
    {"watcher": "nome_especifico", "publicacoes": [...], "cnjs": [...]}.
    Sem "watcher", roda os 3. Sem "publicacoes" explícita, usa o fixture
    de demonstração embutido (só pro publication_watcher)."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    watcher_especifico = body.get('watcher')
    publicacoes = body.get('publicacoes') or _fixture_publicacoes_exemplo()
    cnjs = body.get('cnjs')

    if watcher_especifico:
        from .watchers.scheduler import rodar_watcher
        resultado = await rodar_watcher(db, watcher_especifico, publicacoes_fixture=publicacoes, cnjs_conhecidos=cnjs)
        return {'overall_status': resultado.get('status'), 'watchers': {watcher_especifico: resultado}}

    from .watchers.scheduler import rodar_todos_os_watchers
    return await rodar_todos_os_watchers(db, publicacoes_fixture=publicacoes, cnjs_conhecidos=cnjs)


@app.get('/api/watchers/runs', dependencies=[Depends(verify_internal_token)])
def watchers_runs_list(limit: int = 50, db: Session = Depends(get_db)):
    runs = db.query(WatcherRun).order_by(WatcherRun.id.desc()).limit(limit).all()
    return [{
        'id': r.id, 'watcher_name': r.watcher_name, 'status': r.status,
        'started_at': r.started_at.isoformat(), 'finished_at': r.finished_at.isoformat() if r.finished_at else None,
        'total_publications': r.total_publications, 'total_matches': r.total_matches,
        'total_leads_created': r.total_leads_created, 'error': r.error,
    } for r in runs]


@app.get('/api/watchers/runs/{run_id}', dependencies=[Depends(verify_internal_token)])
def watchers_run_detail(run_id: int, db: Session = Depends(get_db)):
    run = db.query(WatcherRun).filter(WatcherRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f'WatcherRun {run_id} não encontrado.')
    hits = db.query(PublicationHit).filter(PublicationHit.watcher_run_id == run_id).all()
    return {
        'id': run.id, 'watcher_name': run.watcher_name, 'status': run.status,
        'total_publications': run.total_publications, 'total_matches': run.total_matches,
        'total_leads_created': run.total_leads_created, 'error': run.error,
        'hits': [{'id': h.id, 'tribunal': h.tribunal, 'signal_type': h.signal_type, 'normalized_cnj': h.normalized_cnj, 'matched_terms': h.matched_terms} for h in hits],
    }


@app.get('/api/leads', dependencies=[Depends(verify_internal_token)])
def leads_list(status: str | None = None, priority: str | None = None, limit: int = 100, db: Session = Depends(get_db)):
    query = db.query(OpportunityLead)
    if status:
        query = query.filter(OpportunityLead.status == status)
    if priority:
        query = query.filter(OpportunityLead.priority == priority)
    leads = query.order_by(OpportunityLead.confidence_score.desc()).limit(limit).all()
    return [{
        'id': l.id, 'created_at': l.created_at.isoformat(), 'tribunal': l.tribunal,
        'normalized_cnj': l.normalized_cnj, 'signal_type': l.signal_type, 'priority': l.priority,
        'confidence_score': l.confidence_score, 'status': l.status, 'next_action': l.next_action,
        'bot_job_id': l.bot_job_id,
    } for l in leads]


@app.get('/api/leads/{lead_id}', dependencies=[Depends(verify_internal_token)])
def lead_detail(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(OpportunityLead).filter(OpportunityLead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail=f'Lead {lead_id} não encontrado.')
    return {
        'id': lead.id, 'created_at': lead.created_at.isoformat(), 'source': lead.source,
        'process_number': lead.process_number, 'normalized_cnj': lead.normalized_cnj, 'tribunal': lead.tribunal,
        'debtor': lead.debtor, 'signal_type': lead.signal_type, 'confidence_score': lead.confidence_score,
        'priority': lead.priority, 'status': lead.status, 'bot_job_id': lead.bot_job_id,
        'dossie_url': lead.dossie_url, 'next_action': lead.next_action,
    }


@app.post('/api/leads/{lead_id}/run-bots', dependencies=[Depends(verify_internal_token)])
async def lead_run_bots(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(OpportunityLead).filter(OpportunityLead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail=f'Lead {lead_id} não encontrado.')
    if not lead.normalized_cnj:
        raise HTTPException(status_code=400, detail='Lead sem CNJ — não há o que consultar automaticamente.')

    from .bots.runner import executar_bots
    bots_resultado = await executar_bots(lead.normalized_cnj, None, lead.tribunal, 'completo', db=db)
    job = BotJob(
        input_original=lead.normalized_cnj, tipo_identificado=bots_resultado['tipo_identificado'],
        objetivo='completo', status=bots_resultado['status'], resumo_humano=bots_resultado['resumo_humano'],
        proxima_acao=bots_resultado['proxima_acao_recomendada'], raw=bots_resultado,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    for passo in bots_resultado['bots_executados']:
        evidence_ids = passo.get('evidence_ids') or []
        db.add(BotStep(
            job_id=job.id, bot_name=passo['bot_id'], status=passo['status'],
            finished_at=datetime.now(timezone.utc) if passo['status'] != 'waiting_user' else None,
            resultado=passo.get('resultado'), warning='; '.join(passo.get('warnings') or []) or None,
            next_action=passo.get('next_action'), evidence_id=evidence_ids[0] if evidence_ids else None,
        ))
    db.commit()

    lead.bot_job_id = job.id
    lead.dossie_url = f'/api/bots/jobs/{job.id}/dossie'
    db.commit()

    return {'lead_id': lead.id, 'bot_job_id': job.id, 'dossie_url': lead.dossie_url, 'status': bots_resultado['status']}


@app.post('/api/leads/{lead_id}/dismiss', dependencies=[Depends(verify_internal_token)])
def lead_dismiss(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(OpportunityLead).filter(OpportunityLead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail=f'Lead {lead_id} não encontrado.')
    lead.status = 'descartado'
    db.commit()
    return {'lead_id': lead.id, 'status': lead.status}


@app.post('/api/leads/{lead_id}/mark-contacted', dependencies=[Depends(verify_internal_token)])
def lead_mark_contacted(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(OpportunityLead).filter(OpportunityLead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail=f'Lead {lead_id} não encontrado.')
    lead.status = 'contatado'
    db.commit()
    return {'lead_id': lead.id, 'status': lead.status}


@app.get('/api/leads/{lead_id}/dossie', response_class=HTMLResponse)
def lead_dossie(lead_id: int, request: Request, db: Session = Depends(get_db)):
    """v32.1 — dossiê do lead em si, funciona mesmo antes de rodar bots
    (achado real: só existia dossiê do BotJob, que exige ter rodado bots
    primeiro — agora o lead tem uma página própria desde o momento em
    que é criado)."""
    if settings.app_login_password and not _has_valid_session(request):
        return RedirectResponse(url='/login', status_code=303)
    lead = db.query(OpportunityLead).filter(OpportunityLead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail=f'Lead {lead_id} não encontrado.')
    status_labels = {'novo': 'Novo', 'contatado': 'Contatado', 'descartado': 'Descartado'}
    prioridade_labels = {'alta': 'Alta', 'media': 'Média', 'baixa': 'Baixa'}
    from .services.whatsapp_intake import mascarar_documentos_no_texto
    texto_mascarado = mascarar_documentos_no_texto(lead.publication_text) if lead.publication_text else None
    return templates.TemplateResponse(request, 'lead_dossie.html', {
        'lead': lead, 'status_label': status_labels.get(lead.status, lead.status),
        'prioridade_label': prioridade_labels.get(lead.priority, lead.priority),
        'publication_text_mascarado': texto_mascarado,
    })


@app.get('/api/whatsapp/webhook')
def whatsapp_webhook_verify(request: Request):
    """Verificação do webhook da Meta (WhatsApp Business Cloud API) —
    endpoint preparado, não ativado. Ativar exige token de verificação
    próprio configurado (WHATSAPP_VERIFY_TOKEN), que ainda não existe."""
    params = request.query_params
    settings_local = get_settings()
    verify_token = getattr(settings_local, 'whatsapp_verify_token', '') or ''
    if verify_token and params.get('hub.verify_token') == verify_token:
        return int(params.get('hub.challenge', 0))
    raise HTTPException(status_code=403, detail='WhatsApp Business Cloud API ainda não configurado (WHATSAPP_VERIFY_TOKEN vazio).')


@app.post('/api/whatsapp/webhook')
async def whatsapp_webhook_receive(request: Request, db: Session = Depends(get_db)):
    """Recebe mensagens do WhatsApp Business Cloud API — preparado, não
    ativado nesta versão (decisão do usuário: não ativar WhatsApp Business
    agora). Quando ativado, deveria extrair o texto da mensagem do payload
    da Meta e processar igual ao endpoint manual."""
    raise HTTPException(status_code=501, detail='Webhook do WhatsApp Business ainda não ativado — use /api/intake/whatsapp/manual por enquanto.')


@app.get('/api/bots/jobs/{job_id}/dossie', response_class=HTMLResponse)
def bots_job_dossie(job_id: int, request: Request, db: Session = Depends(get_db)):
    """Página HTML do que os bots fizeram num job — input, tipo, status
    geral, cada bot com seu status/evidência/próxima ação."""
    if settings.app_login_password and not _has_valid_session(request):
        return RedirectResponse(url='/login', status_code=303)
    job = db.query(BotJob).filter(BotJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f'Job {job_id} não encontrado.')
    steps = db.query(BotStep).filter(BotStep.job_id == job_id).all()
    status_labels = {
        'concluido': 'Concluído', 'falhou': 'Falhou', 'pendente': 'Pendente', 'waiting_user': 'Aguardando você',
        'completed': 'Concluído', 'partial': 'Parcial', 'failed': 'Falhou',
    }
    return templates.TemplateResponse(request, 'bots_dossie.html', {
        'job': job, 'steps': steps, 'status_labels': status_labels,
        'status_label': status_labels.get(job.status, job.status),
    })


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


@app.get('/api/stj-precatorios/official-files', dependencies=[Depends(verify_internal_token)])
def stj_official_files_list(db: Session = Depends(get_db)):
    """Lista os arquivos oficiais do STJ conhecidos/já baixados pelo StjBot."""
    from .models import StjOfficialFile
    arquivos = db.query(StjOfficialFile).order_by(StjOfficialFile.id.desc()).all()
    return [{
        'id': a.id, 'year': a.year, 'natureza': a.natureza, 'entidade_devedora': a.entidade_devedora,
        'source_url': a.source_url, 'filename': a.original_filename,
        'downloaded_at': a.downloaded_at.isoformat() if a.downloaded_at else None,
        'row_count': a.row_count, 'status': a.status, 'error': a.error,
    } for a in arquivos]


@app.post('/api/stj-precatorios/sync', dependencies=[Depends(verify_internal_token)])
async def stj_official_sync(db: Session = Depends(get_db)):
    """Força o StjBot a buscar/baixar os arquivos oficiais públicos do STJ
    agora — sem esperar upload manual. Se não conseguir acessar a página ou
    baixar nenhum arquivo, devolve isso honestamente, sem fingir sucesso."""
    from .services.stj_official_scraper import sync_official_files
    return await sync_official_files(db)


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
def stj_search(request: StjSearchRequest, db: Session = Depends(get_db)):
    """Busca nos arquivos oficiais do STJ que já foram enviados via
    /api/stj-precatorios/upload-xlsx. Nunca cai para dado sintético: se
    nenhum arquivo foi carregado ainda, devolve status 'not_loaded' com a
    mensagem 'Arquivo oficial do STJ ainda não carregado.'
    """
    resultado = stj_uploads.search_uploaded_files(request.search_type, request.search_key, request.ano_orcamento)

    if resultado.get('status') == 'not_loaded':
        proxima_acao = 'Arquivo oficial do STJ ainda não carregado. Envie o XLSX antes de buscar.'
        pendencias = ['Carregar o XLSX oficial do STJ.']
        resumo = 'STJ consultado, mas nenhum arquivo foi carregado ainda.'
        confirmados = []
    elif resultado.get('results'):
        resumo = f"{len(resultado['results'])} registro(s) encontrado(s) no STJ."
        proxima_acao = 'Dado encontrado nos arquivos oficiais do STJ que você já carregou.'
        pendencias = []
        confirmados = resultado['results']
    else:
        resumo = 'STJ consultado nos arquivos carregados, sem resultado para esse dado.'
        proxima_acao = 'Não encontramos esse dado nos arquivos do STJ já carregados. Confira o valor ou tente outro dado.'
        pendencias = []
        confirmados = []

    log = _salvar_diligencia(
        db, input_original=request.search_key, tipo_identificado=f'stj_{request.search_type}',
        valor_normalizado=request.search_key, objetivo='precatorio',
        resumo_humano=resumo, proxima_acao_recomendada=proxima_acao,
        resultados_confirmados=confirmados, pendencias=pendencias, raw_avancado=resultado,
    )
    resultado['diligencia_id'] = log.id
    return resultado


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

    documento_mascarado = mask_document(request.document) if request.document else (request.name or request.source_id)
    log = _salvar_diligencia(
        db, input_original=documento_mascarado, tipo_identificado=f'certidao_{request.certificate_type}',
        valor_normalizado=documento_mascarado, objetivo='certidao',
        resumo_humano=result.get('message'), proxima_acao_recomendada=result.get('message'),
        pendencias=[result.get('message')] if result.get('status') not in {'negativa', 'positiva'} else [],
        fontes_manuais_recomendadas=[{'fonte': request.source_id, 'acao': 'Abrir link oficial'}] if result.get('fonte_url') else [],
        raw_avancado=result,
    )
    return {'id': record.id, 'created_at': record.created_at.isoformat(), 'diligencia_id': log.id, **result}


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
