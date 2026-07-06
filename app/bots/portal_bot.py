"""PortalBot: automação real de navegador (Playwright) contra um portal
público oficial. Reaproveita captcha_relay.py inteiramente — não duplica
lógica de abrir navegador, preencher campo ou detectar captcha.

IMPORTANTE, honesto: este bot NÃO tem um alvo com seletores de campo
validados nesta entrega. O sandbox onde isso foi desenvolvido não alcança
domínios externos gerais (só GitHub/PyPI/npm) — não dá pra abrir o portal
real e inspecionar o HTML dos campos de formulário daqui. O que FOI possível
confirmar:

- https://processual.trf1.jus.br/ permite fetch automatizado (robots.txt não
  bloqueia), diferente de https://certidoesunificadas.app.tjpe.jus.br/, cujo
  robots.txt EXPLICITAMENTE proíbe acesso automatizado — por isso o TJPE
  (que a nota antiga do registry sugeria como alvo) está fora de cogitação
  aqui; usá-lo violaria a regra permanente deste projeto ("robots.txt é
  linha vermelha").
- O mecanismo em si (captcha_relay.start_browser_session/solve_captcha_session)
  já é real, já foi testado neste projeto, e já está exposto via
  /api/portal-automation/start e /solve.

Portanto: PortalBot funciona de verdade para QUALQUER url/fill_fields/
submit_selector que você fornecer (útil pra qualquer fonte já com robots.txt
liberado). Ele só não vem com um alvo pré-configurado e testado nesta
entrega — isso exige uma pessoa com acesso de navegador real (ou o próprio
Render em produção) inspecionando o HTML do formulário uma vez, pra
confirmar os seletores exatos.
"""
from __future__ import annotations

from typing import Any

from .base import BaseBot, BotResult
from ..services import captcha_relay
from ..config import get_settings


class PortalBot(BaseBot):
    bot_id = 'portal_bot'
    nome = 'PortalBot'
    finalidade = 'Mecanismo pronto, requer alvo configurado (URL + seletores de campo) — abre portal público oficial, preenche campos e tenta consultar; pausa em captcha pra intervenção humana.'

    def can_run(self, tipo_identificado: str, objetivo: str) -> bool:
        return False  # nunca acionado automaticamente pelo runner — precisa de url/fill_fields explícitos, chamado via run_com_alvo()

    async def run(self, *, valor: str, uf: str | None, tribunal: str | None, objetivo: str) -> BotResult:
        return BotResult(
            bot_id=self.bot_id, nome=self.nome, status='pendente',
            next_action='PortalBot precisa de uma URL e mapeamento de campos explícitos — use run_com_alvo(url, fill_fields, submit_selector).',
        )

    async def run_com_alvo(self, source_id: str, url: str, fill_fields: dict[str, str], submit_selector: str) -> BotResult:
        settings = get_settings()
        resultado = await captcha_relay.start_browser_session(
            source_id, url, fill_fields, submit_selector,
            chrome_executable_path=settings.playwright_chrome_path or None,
        )
        status_map = {
            'success': 'concluido',
            'captcha_required': 'waiting_user',
            'unsupported_captcha_type': 'pendente',
            'source_error': 'falhou',
        }
        status = status_map.get(resultado.get('status'), 'falhou')

        if status == 'waiting_user':
            return BotResult(
                bot_id=self.bot_id, nome=self.nome, status=status,
                resultado=resultado,
                session_id=resultado.get('session_id'),
                captcha_image_base64=resultado.get('captcha_image_base64'),
                next_action='Esta etapa precisa de validação manual. Resolva o captcha e chame /api/bots/jobs/{id}/resume com o texto.',
                pendencias=['Captcha clássico detectado — aguardando resolução humana.'],
            )
        if status == 'concluido':
            return BotResult(bot_id=self.bot_id, nome=self.nome, status=status, resultado=resultado, next_action='Consulta concluída. Confira o HTML capturado e registre como evidência se relevante.')
        if resultado.get('status') == 'unsupported_captcha_type':
            return BotResult(
                bot_id=self.bot_id, nome=self.nome, status='pendente', resultado=resultado,
                pendencias=['Este portal usa reCAPTCHA/hCaptcha — não é possível automatizar; consulte manualmente pelo link oficial.'],
                next_action=resultado.get('message'),
            )
        return BotResult(bot_id=self.bot_id, nome=self.nome, status='falhou', resultado=resultado, warnings=[resultado.get('message', 'Falha desconhecida.')], next_action=resultado.get('message'))

    async def resume(self, session_id: str, captcha_text: str) -> BotResult:
        resultado = await captcha_relay.solve_captcha_session(session_id, captcha_text)
        status_map = {'success': 'concluido', 'captcha_rejected': 'pendente', 'session_expired': 'falhou', 'source_error': 'falhou'}
        status = status_map.get(resultado.get('status'), 'falhou')
        next_action = {
            'concluido': 'Consulta concluída. Confira o HTML capturado e registre como evidência se relevante.',
            'pendente': 'Captcha rejeitado — a sessão foi encerrada. Recomece a consulta.',
            'falhou': resultado.get('message', 'Sessão expirada ou erro — recomece a consulta.'),
        }.get(status)
        return BotResult(bot_id=self.bot_id, nome=self.nome, status=status, resultado=resultado, next_action=next_action)
