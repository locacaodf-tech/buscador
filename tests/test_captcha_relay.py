import asyncio
import os
from pathlib import Path

import pytest

from app.services import captcha_relay

CHROME_PATH = os.environ.get(
    'TEST_CHROME_PATH',
    '/home/claude/.cache/puppeteer/chrome/linux-131.0.6778.204/chrome-linux64/chrome',
)
FIXTURE_URL = 'file://' + str(Path(__file__).parent / 'fixtures' / 'mock_captcha_form.html')

pytestmark = pytest.mark.skipif(
    not Path(CHROME_PATH).exists(),
    reason='Chrome de teste não encontrado neste ambiente — mecanismo requer navegador real instalado.',
)


def test_deteccao_de_captcha_classico_para_e_devolve_imagem():
    async def _run():
        result = await captcha_relay.start_browser_session(
            source_id='teste_fixture',
            url=FIXTURE_URL,
            fill_fields={'#documento': '12345678900'},
            submit_selector='#btnSubmit',
            chrome_executable_path=CHROME_PATH,
        )
        assert result['status'] == 'captcha_required'
        assert 'session_id' in result
        assert len(result['captcha_image_base64']) > 100  # print real da imagem, não vazio
        assert captcha_relay.active_session_count() == 1

        session = captcha_relay.SESSIONS.pop(result['session_id'])
        await session.browser.close()
        await session.playwright.stop()
    asyncio.run(_run())


def test_resolver_captcha_com_codigo_certo_completa_com_sucesso():
    async def _run():
        start = await captcha_relay.start_browser_session(
            source_id='teste_fixture',
            url=FIXTURE_URL,
            fill_fields={'#documento': '12345678900'},
            submit_selector='#btnSubmit',
            chrome_executable_path=CHROME_PATH,
        )
        assert start['status'] == 'captcha_required'

        resolved = await captcha_relay.solve_captcha_session(start['session_id'], 'K9R2X')
        assert resolved['status'] == 'success'
        assert 'Consulta de teste bem-sucedida' in resolved['html']
        assert '12345678900' in resolved['html']
        assert captcha_relay.active_session_count() == 0
    asyncio.run(_run())


def test_resolver_captcha_com_codigo_errado_reporta_rejeicao():
    async def _run():
        start = await captcha_relay.start_browser_session(
            source_id='teste_fixture',
            url=FIXTURE_URL,
            fill_fields={'#documento': '12345678900'},
            submit_selector='#btnSubmit',
            chrome_executable_path=CHROME_PATH,
        )
        resolved = await captcha_relay.solve_captcha_session(start['session_id'], 'ERRADO')
        assert resolved['status'] == 'captcha_rejected'
    asyncio.run(_run())


def test_sessao_inexistente_retorna_expirada():
    async def _run():
        result = await captcha_relay.solve_captcha_session('nao-existe-esse-id', 'ABC12')
        assert result['status'] == 'session_expired'
    asyncio.run(_run())


def test_url_invalida_nao_quebra_retorna_erro_amigavel():
    async def _run():
        result = await captcha_relay.start_browser_session(
            source_id='teste_fixture',
            url='file:///caminho/que/nao/existe.html',
            fill_fields={},
            submit_selector='#btnSubmit',
            chrome_executable_path=CHROME_PATH,
        )
        assert result['status'] == 'source_error'
        assert captcha_relay.active_session_count() == 0
    asyncio.run(_run())


def test_recaptcha_nunca_tenta_resolver_avisa_tipo_nao_suportado():
    recaptcha_url = 'file://' + str(Path(__file__).parent / 'fixtures' / 'mock_recaptcha_form.html')

    async def _run():
        result = await captcha_relay.start_browser_session(
            source_id='teste_fixture_recaptcha',
            url=recaptcha_url,
            fill_fields={'#documento': '12345678900'},
            submit_selector='#btnSubmit',
            chrome_executable_path=CHROME_PATH,
        )
        assert result['status'] == 'unsupported_captcha_type'
        assert 'reCAPTCHA' in result['message']
        assert 'session_id' not in result  # nunca abre sessão pra algo que não sabe resolver
        assert captcha_relay.active_session_count() == 0  # navegador já foi fechado, não ficou pendurado
    asyncio.run(_run())
