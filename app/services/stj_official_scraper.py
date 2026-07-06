"""StjBot executor real (v30.2): baixa automaticamente os arquivos oficiais
XLSX/XLSM de precatórios do STJ, direto da página pública, sem precisar de
navegação intermediária — a página real (verificada em 2026-07-06 via
fetch direto, ver RELATORIO_V30_2) já lista links diretos pros arquivos,
sem passar por página HTML intermediária nenhuma.

Importante, honesto: este módulo faz requisições HTTP simples (GET) contra
um domínio público oficial (stj.jus.br), baixando arquivos que já são
publicados abertamente para download por qualquer pessoa — não há login,
captcha, nem bypass de nenhum mecanismo de proteção. O sandbox onde isso
foi desenvolvido não alcança domínios externos gerais (só GitHub/PyPI/npm),
então o download ao vivo só pode ser confirmado em produção (Render) ou
localmente fora deste sandbox — os testes aqui usam um fixture HTML fiel
ao conteúdo real da página (obtido via fetch direto durante o
desenvolvimento), não uma estrutura inventada.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STJ_PRECATORIOS_PAGE_URL = 'https://www.stj.jus.br/sites/portalp/Processos/precatorios'
FILE_EXTENSIONS = ('.xlsx', '.xlsm', '.xls', '.csv')

# User-Agent identificado (não se passa por navegador) e um limite de
# arquivos por sync, pra nunca sobrecarregar o servidor público de uma vez.
USER_AGENT = 'buscador-processos-meuprecatorioBR/1.0 (uso interno; contato via github.com/locacaodf-tech/buscador)'
MAX_FILES_PER_SYNC = 8


def extract_official_file_links(html: str, base_url: str = STJ_PRECATORIOS_PAGE_URL) -> list[dict[str, Any]]:
    """Extrai os links de arquivo (XLSX/XLSM/XLS/CSV) do HTML da página de
    precatórios do STJ, com o texto/contexto ao redor de cada link (usado
    depois pra inferir ano/natureza/entidade). Função pura — testável com
    qualquer HTML, sem precisar de rede."""
    encontrados = []
    # Captura <a href="...ext">texto</a>, mantendo href e texto do link.
    padrao = re.compile(
        r'<a\s+[^>]*href=["\']([^"\']+\.(?:xlsx|xlsm|xls|csv))["\'][^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    for match in padrao.finditer(html):
        url, texto_bruto = match.group(1), match.group(2)
        texto = re.sub(r'<[^>]+>', ' ', texto_bruto)
        texto = re.sub(r'\s+', ' ', texto).strip()
        if url.startswith('/'):
            from urllib.parse import urljoin
            url = urljoin(base_url, url)
        if not url.startswith('http'):
            continue
        encontrados.append({'url': url, 'texto_link': texto, 'filename': url.rsplit('/', 1)[-1]})
    return encontrados


def infer_metadata_from_context(link: dict[str, Any], html_before_link: str = '') -> dict[str, Any]:
    """Tenta inferir ano/natureza/entidade a partir do texto do link e do
    que vem escrito logo antes dele na página (ex.: '2026 - inclusos na
    proposta orçamentária de 2027'). Sempre honesto: campos que não dá pra
    inferir ficam None, nunca um palpite disfarçado de fato."""
    texto = (link.get('texto_link') or '') + ' ' + (html_before_link or '')
    ano_match = re.search(r'\b(20\d{2})\b', texto)
    ano = int(ano_match.group(1)) if ano_match else None

    natureza = None
    if re.search(r'aliment', texto, re.IGNORECASE):
        natureza = 'alimentar'
    elif re.search(r'comum', texto, re.IGNORECASE):
        natureza = 'comum'

    entidade = None
    for candidato in ['União', 'INSS', 'Fazenda Nacional', 'Universidade Federal de Ouro Preto']:
        if candidato.lower() in texto.lower():
            entidade = candidato
            break

    return {'year': ano, 'natureza': natureza, 'entidade_devedora': entidade}


async def fetch_precatorios_page() -> str:
    """Busca o HTML real da página de precatórios do STJ. Levanta exceção
    se não conseguir — quem chama decide o que fazer com isso (nunca
    inventa conteúdo)."""
    import httpx
    async with httpx.AsyncClient(timeout=20, headers={'User-Agent': USER_AGENT}, follow_redirects=True) as client:
        resp = await client.get(STJ_PRECATORIOS_PAGE_URL)
        resp.raise_for_status()
        return resp.text


async def download_file(url: str) -> bytes:
    import httpx
    async with httpx.AsyncClient(timeout=30, headers={'User-Agent': USER_AGENT}, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


def official_files_dir() -> Path:
    from ..config import get_settings
    configured = getattr(get_settings(), 'stj_upload_dir', '') or 'data/stj_uploads'
    directory = Path(configured) / 'oficial_sync'
    directory.mkdir(parents=True, exist_ok=True)
    return directory


async def sync_official_files(db, max_files: int = MAX_FILES_PER_SYNC, html_override: str | None = None) -> dict[str, Any]:
    """Ponto de entrada principal: busca a página, extrai links, baixa cada
    arquivo (até max_files), salva StjOfficialFile pra cada tentativa
    (sucesso ou falha), e roda o parser existente nos arquivos baixados
    com sucesso. html_override é só pra teste (injeta o fixture sem rede)."""
    from ..models import StjOfficialFile
    from ..connectors.stj_precatorios import parse_workbook_bytes
    from ..connectors.stj_precatorios import infer_file_metadata

    resultado = {'status': 'ok', 'arquivos_processados': [], 'erro_pagina': None, 'total_registros_novos': 0}

    try:
        html = html_override if html_override is not None else await fetch_precatorios_page()
    except Exception as exc:
        resultado['status'] = 'falhou_acessar_pagina'
        resultado['erro_pagina'] = str(exc)
        return resultado

    links = extract_official_file_links(html)
    if not links:
        resultado['status'] = 'nenhum_arquivo_encontrado'
        return resultado

    diretorio = official_files_dir()
    for link in links[:max_files]:
        meta = infer_metadata_from_context(link)
        registro = StjOfficialFile(
            year=meta['year'], natureza=meta['natureza'], entidade_devedora=meta['entidade_devedora'],
            source_url=link['url'], original_filename=link['filename'], status='pending',
        )
        try:
            conteudo = await download_file(link['url'])
            caminho_local = diretorio / link['filename']
            caminho_local.write_bytes(conteudo)
            file_hash = hashlib.sha256(conteudo).hexdigest()

            file_meta = infer_file_metadata(link['filename'], link.get('texto_link', ''))
            registros_parseados = parse_workbook_bytes(conteudo, file_meta, link['url'])

            registro.local_path = str(caminho_local)
            registro.downloaded_at = datetime.now(timezone.utc)
            registro.file_hash = file_hash
            registro.row_count = len(registros_parseados)
            registro.status = 'downloaded'
            resultado['total_registros_novos'] += len(registros_parseados)
        except Exception as exc:
            registro.status = 'failed'
            registro.error = str(exc)

        db.add(registro)
        resultado['arquivos_processados'].append({
            'url': link['url'], 'filename': link['filename'], 'status': registro.status,
            'row_count': registro.row_count, 'error': registro.error,
        })
    db.commit()

    if not any(a['status'] == 'downloaded' for a in resultado['arquivos_processados']):
        resultado['status'] = 'falhou_baixar_todos'

    return resultado


def registros_de_arquivos_baixados(db) -> list[dict[str, Any]]:
    """Lê os registros já baixados com sucesso e devolve os dados
    parseados, pra busca por sequencial/nome/CNJ reaproveitar sem baixar
    de novo a cada consulta."""
    from ..models import StjOfficialFile
    from ..connectors.stj_precatorios import parse_workbook_bytes
    from ..connectors.stj_precatorios import infer_file_metadata

    arquivos = db.query(StjOfficialFile).filter(StjOfficialFile.status == 'downloaded').all()
    todos_registros = []
    for arquivo in arquivos:
        if not arquivo.local_path or not Path(arquivo.local_path).exists():
            continue
        conteudo = Path(arquivo.local_path).read_bytes()
        file_meta = infer_file_metadata(arquivo.original_filename or '')
        todos_registros += parse_workbook_bytes(conteudo, file_meta, arquivo.source_url)
    return todos_registros
