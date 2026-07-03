from __future__ import annotations

import base64
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

SESSION_TTL_SECONDS = 5 * 60  # sessão expira em 5 min se ninguém resolver o captcha

# Captchas clássicos (imagem com texto distorcido + campo pra digitar) — este
# mecanismo funciona para eles. reCAPTCHA/hCaptcha são widgets de desafio
# comportamental, não "digite o texto que vê" — não dá pra resolver preenchendo
# um campo de texto, então são detectados e reportados separadamente, nunca
# tratados como se este mecanismo os resolvesse.
CAPTCHA_IMAGE_SELECTORS = [
    'img[alt*="captcha" i]', 'img[id*="captcha" i]', 'img[src*="captcha" i]', 'img[class*="captcha" i]',
]
CAPTCHA_INPUT_SELECTORS = [
    'input[name*="captcha" i]', 'input[id*="captcha" i]', 'input[placeholder*="captcha" i]',
    'input[name*="codigo" i]', 'input[id*="codigo" i]',
]
RECAPTCHA_SELECTORS = ['.g-recaptcha', 'iframe[src*="recaptcha" i]', '.h-captcha', 'iframe[src*="hcaptcha" i]']


@dataclass
class BrowserSession:
    session_id: str
    source_id: str
    playwright: Any
    browser: Any
    page: Any
    created_at: float
    captcha_input_selector: str
    submit_selector: str


SESSIONS: dict[str, BrowserSession] = {}


async def _cleanup_expired() -> None:
    now = time.time()
    expired = [sid for sid, s in SESSIONS.items() if now - s.created_at > SESSION_TTL_SECONDS]
    for sid in expired:
        session = SESSIONS.pop(sid, None)
        if session:
            try:
                await session.browser.close()
                await session.playwright.stop()
            except Exception:
                pass


async def detect_captcha(page) -> dict[str, Any] | None:
    """Verifica se a página tem uma imagem de captcha clássico + campo pra
    digitar o código. Retorna None se não achar (fluxo segue sem parar)."""
    for img_sel in CAPTCHA_IMAGE_SELECTORS:
        img = await page.query_selector(img_sel)
        if not img:
            continue
        for input_sel in CAPTCHA_INPUT_SELECTORS:
            inp = await page.query_selector(input_sel)
            if inp:
                screenshot_bytes = await img.screenshot()
                return {
                    'image_base64': base64.b64encode(screenshot_bytes).decode('ascii'),
                    'input_selector': input_sel,
                }
    return None


async def detect_recaptcha(page) -> bool:
    for sel in RECAPTCHA_SELECTORS:
        if await page.query_selector(sel):
            return True
    return False


async def start_browser_session(
    source_id: str,
    url: str,
    fill_fields: dict[str, str],
    submit_selector: str,
    chrome_executable_path: str | None = None,
) -> dict[str, Any]:
    """Abre o navegador, navega, preenche os campos dados, e:
    - se achar reCAPTCHA/hCaptcha: para e avisa que este mecanismo não serve
      pra esse tipo de desafio (não é 'digite o texto', é comportamental);
    - se achar captcha clássico (imagem + campo texto): PARA, tira print e
      devolve pro usuário resolver — nunca resolve sozinho;
    - se não achar nenhum: segue e submete direto, devolve o resultado.
    """
    await _cleanup_expired()
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    launch_kwargs: dict[str, Any] = {'headless': True}
    if chrome_executable_path:
        launch_kwargs['executable_path'] = chrome_executable_path
    browser = await pw.chromium.launch(**launch_kwargs)
    page = await browser.new_page()

    try:
        await page.goto(url, wait_until='networkidle', timeout=30000)
    except Exception as exc:
        await browser.close()
        await pw.stop()
        return {'status': 'source_error', 'message': f'Não consegui abrir {url}: {exc}'}

    for selector, value in fill_fields.items():
        try:
            await page.fill(selector, value)
        except Exception:
            pass  # campo pode não existir nesta variação do formulário — segue sem travar tudo

    if await detect_recaptcha(page):
        await browser.close()
        await pw.stop()
        return {
            'status': 'unsupported_captcha_type',
            'message': (
                'Esta página usa reCAPTCHA/hCaptcha — um desafio comportamental, não "digite o texto que vê". '
                'O mecanismo de pausa-e-retomada aqui só resolve captchas clássicos de imagem+texto. '
                'Para este site, a consulta precisa ser feita manualmente.'
            ),
        }

    captcha = await detect_captcha(page)
    if captcha:
        session_id = str(uuid.uuid4())
        SESSIONS[session_id] = BrowserSession(
            session_id=session_id, source_id=source_id, playwright=pw, browser=browser, page=page,
            created_at=time.time(), captcha_input_selector=captcha['input_selector'], submit_selector=submit_selector,
        )
        return {
            'status': 'captcha_required',
            'session_id': session_id,
            'captcha_image_base64': captcha['image_base64'],
            'expires_in_seconds': SESSION_TTL_SECONDS,
        }

    try:
        await page.click(submit_selector)
        await page.wait_for_load_state('networkidle', timeout=15000)
        html = await page.content()
    except Exception as exc:
        await browser.close()
        await pw.stop()
        return {'status': 'source_error', 'message': f'Falha ao submeter formulário: {exc}'}

    await browser.close()
    await pw.stop()
    return {'status': 'success', 'html': html}


async def solve_captcha_session(session_id: str, captcha_text: str) -> dict[str, Any]:
    """Retoma uma sessão pausada: digita o texto que o HUMANO resolveu (nunca
    resolvido por código) e submete. Fecha a sessão de qualquer forma —
    sucesso ou erro, sessão de navegador não fica pendurada."""
    session = SESSIONS.pop(session_id, None)
    if not session:
        return {'status': 'session_expired', 'message': 'Sessão expirada ou inexistente (tempo limite: 5 minutos). Recomece a consulta.'}

    page = session.page
    try:
        await page.fill(session.captcha_input_selector, captcha_text)
        await page.click(session.submit_selector)
        await page.wait_for_load_state('networkidle', timeout=15000)
        html = await page.content()
        # Remove <script>/<style> antes de checar rejeição — código-fonte JS
        # frequentemente contém o texto da mensagem de erro como string,
        # independente do resultado real (achado testando este próprio
        # mecanismo). Checar só o texto visível evita falso positivo.
        html_sem_script = re.sub(r'<script\b[^>]*>.*?</script>', ' ', html, flags=re.I | re.S)
        html_sem_script = re.sub(r'<style\b[^>]*>.*?</style>', ' ', html_sem_script, flags=re.I | re.S)
        rejected = bool(re.search(r'captcha\s+inv[aá]lido|c[oó]digo\s+incorreto|captcha\s+incorreto', html_sem_script, re.IGNORECASE))
        return {'status': 'captcha_rejected' if rejected else 'success', 'html': html}
    except Exception as exc:
        return {'status': 'source_error', 'message': f'Falha ao retomar após captcha: {exc}'}
    finally:
        try:
            await session.browser.close()
            await session.playwright.stop()
        except Exception:
            pass


def active_session_count() -> int:
    return len(SESSIONS)
