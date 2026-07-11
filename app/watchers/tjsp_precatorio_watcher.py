"""TJSP Precatório Pendente Watcher — fonte real, verificada:
- URL: https://www.tjsp.jus.br/cac/scp/webRelPublicLstPagPrecatPendentes.aspx
- robots.txt do TJSP verificado em 2026-07-10: NÃO bloqueia /cac/ nem
  /Precatorios/ (só /Segmento/, /Concursos/, /Nugep/, /Handlers).
- Prática de scraping do TJSP confirmada como aceita por terceiros
  independentes (pacote acadêmico "tjsp" em R, usado publicamente há anos).
- Página é um formulário GeneXus (JS/postback), não uma lista estática
  simples como a do STJ — por isso usa Playwright (mesmo padrão do
  PortalBot), não parsing de HTML cru.

Honestidade importante: não consegui testar a submissão real do
formulário a partir deste sandbox (rede restrita a poucos domínios). O
seletor abaixo foi construído a partir da estrutura REAL da página
(confirmada via fetch direto), mas a submissão completa (escolher
entidade → ver resultado) só pode ser confirmada rodando de verdade no
Render ou localmente fora deste sandbox — mesma limitação que já existia
pro StjBot antes de eu confirmar lá."""
from __future__ import annotations

from typing import Any

from .base import HitEncontrado, WatcherResult

TJSP_PRECATORIOS_PENDENTES_URL = 'https://www.tjsp.jus.br/cac/scp/webRelPublicLstPagPrecatPendentes.aspx'

# Entidades de maior interesse pra começar — evita clicar nas 600+ opções
# do dropdown de uma vez (sobrecarregaria o servidor público à toa).
# Expansível depois que a mecânica estiver confirmada ao vivo.
ENTIDADES_PRIORITARIAS = [
    'FAZENDA DO ESTADO DE SÃO PAULO',
    'INSS - INSTITUTO NACIONAL DO SEGURO SOCIAL',
    'MUNICÍPIO DE SÃO PAULO',
]

USER_AGENT = 'buscador-processos-meuprecatorioBR/1.0 (uso interno; contato via github.com/locacaodf-tech/buscador)'


async def _extrair_tabela_via_playwright(entidade: str) -> list[dict[str, Any]]:
    """Abre a página real do TJSP, seleciona a entidade no dropdown, e
    extrai a tabela de precatórios pendentes resultante. Usa o mesmo
    padrão start()/stop() explícito do captcha_relay.py (achado real:
    'async with async_playwright()' trava/derruba o servidor quando
    chamado de dentro do próprio FastAPI async — o padrão com stop()
    explícito em cada saída é o que já funciona em produção aqui)."""
    from playwright.async_api import async_playwright
    from ..config import get_settings

    settings = get_settings()
    chrome_path = getattr(settings, 'playwright_chrome_path', '') or None

    pw = await async_playwright().start()
    launch_kwargs: dict[str, Any] = {'headless': True}
    if chrome_path:
        launch_kwargs['executable_path'] = chrome_path
    browser = await pw.chromium.launch(**launch_kwargs)
    registros: list[dict[str, Any]] = []
    try:
        page = await browser.new_page(user_agent=USER_AGENT)
        await page.goto(TJSP_PRECATORIOS_PENDENTES_URL, timeout=30000)
        await page.wait_for_load_state('networkidle', timeout=15000)

        # Achado real testando: a página GeneXus não usa <select> nativo
        # pro combo de entidades — tenta select nativo primeiro (rápido se
        # existir), senão cai pra um combo customizado (input + lista).
        selecionou = False
        try:
            select_locator = page.locator('select').first
            await select_locator.select_option(label=entidade, timeout=5000)
            selecionou = True
        except Exception:
            pass

        if not selecionou:
            # Combo customizado GeneXus: geralmente um input de texto que
            # filtra uma lista ao digitar. Tenta digitar o nome da entidade
            # e clicar na primeira opção que aparecer.
            try:
                campo_texto = page.locator('input[type="text"]').first
                await campo_texto.click(timeout=5000)
                await campo_texto.fill(entidade[:20])
                await page.wait_for_timeout(1000)
                opcao = page.get_by_text(entidade, exact=False).first
                await opcao.click(timeout=5000)
                selecionou = True
            except Exception as exc:
                raise RuntimeError(f'Não consegui selecionar a entidade "{entidade}" — mecânica do combo ainda não confirmada: {exc}')

        botao = page.get_by_text('Listar Todos', exact=False).first
        await botao.click(timeout=10000)
        await page.wait_for_load_state('networkidle', timeout=15000)

        linhas = await page.locator('table tr').all()
        for linha in linhas:
            celulas = await linha.locator('td').all_inner_texts()
            if celulas and any(c.strip() for c in celulas):
                registros.append({'entidade': entidade, 'colunas': celulas})
    finally:
        await browser.close()
        await pw.stop()
    return registros


async def varrer_precatorios_pendentes_tjsp(entidades: list[str] | None = None) -> WatcherResult:
    """Ponto de entrada do watcher — varre as entidades prioritárias (ou
    as informadas) e devolve os registros encontrados como hits. Uma
    entidade falhando não derruba as demais."""
    alvo = entidades or ENTIDADES_PRIORITARIAS
    hits: list[HitEncontrado] = []
    falhas = []

    for entidade in alvo:
        try:
            registros = await _extrair_tabela_via_playwright(entidade)
        except Exception as exc:
            falhas.append(f'{entidade}: {exc}')
            continue

        for reg in registros:
            texto = ' | '.join(reg['colunas'])
            hits.append(HitEncontrado(
                source='tjsp_precatorio_watcher', tribunal='TJSP', publication_date=None,
                process_number=None, normalized_cnj=None, parties_text=None, lawyers_text=None,
                publication_text=f'Precatório pendente de pagamento — {entidade}: {texto}',
                matched_terms=['precatorio'], signal_type='precatorio_confirmado', confidence='high',
                source_url=TJSP_PRECATORIOS_PENDENTES_URL,
                raw={'ente_devedor': entidade},
            ))

    status = 'completed' if not falhas else ('partial' if hits else 'failed')
    return WatcherResult(
        watcher_name='tjsp_precatorio_watcher', status=status,
        tribunals_scanned=['TJSP'], total_publications=len(alvo), hits=hits,
        error='; '.join(falhas) if falhas else None,
    )
