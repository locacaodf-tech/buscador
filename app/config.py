from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_env: str = 'local'
    app_secret: str = 'troque-esta-chave'
    database_url: str = 'sqlite:///./buscador_processos.db'

    # Chave pública oficial do DataJud/CNJ — confirmada ao vivo na wiki oficial
    # (datajud-wiki.cnj.jus.br/api-publica/acesso) em 04/07/2026. NÃO é segredo:
    # é a MESMA chave publicada pelo CNJ pra qualquer pessoa usar, documentada
    # oficialmente. O CNJ pode rotacionar essa chave a qualquer momento — se a
    # busca por CNJ começar a falhar com erro de autenticação, confira o valor
    # atual na wiki e sobrescreva via variável de ambiente DATAJUD_API_KEY.
    # Valor que o usuário configurou explicitamente via variável de ambiente
    # DATAJUD_API_KEY. Fica vazio por padrão — quem decide se usa a chave
    # pública padrão ou uma própria é a função resolved_datajud_api_key()
    # abaixo, nunca este campo isolado.
    datajud_api_key: str = ''
    datajud_base_url: str = 'https://api-publica.datajud.cnj.jus.br'
    datajud_timeout_seconds: int = 40
    datajud_page_size: int = 50

    judit_enabled: bool = False
    judit_api_key: str = ''
    judit_requests_base_url: str = 'https://requests.production.judit.io'
    judit_tracking_base_url: str = 'https://tracking.production.judit.io'
    judit_lawsuits_base_url: str = 'https://lawsuits.production.judit.io'
    judit_crawler_base_url: str = 'https://crawler.production.judit.io'
    judit_timeout_seconds: int = 60
    judit_poll_seconds: int = 5
    judit_max_polls: int = 20
    # Valor de search_type enviado à Judit para busca por nome. A doc disponível
    # não deixa 100% claro se é "name" ou "nome" — configurável sem mexer em código.
    judit_name_search_type: str = 'name'

    internal_api_token: str = ''
    # Senha simples para proteger a tela (login por sessão via cookie).
    # Vazio = login desabilitado (comportamento atual, sem gate).
    app_login_password: str = ''
    # Mantém a sessão logada por vários dias para uso prático no iPhone/navegador.
    session_ttl_days: int = 90
    # Origens (domínios) autorizadas por CORS a chamar a API a partir de um
    # frontend publicado separadamente (ex.: HTML estático no Netlify/Vercel).
    # Múltiplas origens separadas por vírgula. Vazio = nenhuma origem cross-origin liberada.
    frontend_allowed_origins: str = ''
    # Pasta local com XLSX do STJ baixados manualmente (modo offline do
    # conector stj_precatorios). Vazio = modo online (baixa da página oficial).
    stj_local_dir: str = ''
    # Pasta onde os XLSX enviados pela tela STJ ficam salvos. Em Render com disco persistente, use /data/stj_uploads.
    stj_upload_dir: str = ''
    # Pasta onde os anexos de evidência manual (PDF/XLSX/print) ficam salvos.
    # Em Render com disco persistente, use /data/evidencias_manuais.
    evidence_upload_dir: str = ''
    # API Serpro Consulta CND (Receita/PGFN) — serviço oficial PAGO, contratado
    # na Loja Serpro. Vazio = conector responde 'requer_api_contratada'.
    serpro_cnd_consumer_key: str = ''
    serpro_cnd_consumer_secret: str = ''
    serpro_cnd_codigo_identificacao: str = ''
    # Automação de navegador com pausa em captcha (captcha_relay.py). Se vazio,
    # usa o Chromium baixado pelo próprio Playwright (playwright install chromium).
    # Aponte para um Chrome/Chromium já instalado no host se preferir não baixar outro.
    playwright_chrome_path: str = ''


def parse_allowed_origins(raw: str) -> list[str]:
    """Converte FRONTEND_ALLOWED_ORIGINS (string separada por vírgula) em lista.

    Função pura, sem depender de Settings, para facilitar teste. Nunca retorna
    "*" implicitamente — string vazia vira lista vazia (nenhuma origem liberada).
    """
    return [origin.strip() for origin in raw.split(',') if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Chave pública oficial do DataJud/CNJ — confirmada ao vivo na wiki oficial
# (datajud-wiki.cnj.jus.br/api-publica/acesso) em 04/07/2026. NÃO é segredo:
# é a MESMA chave publicada pelo CNJ pra qualquer pessoa usar. O CNJ pode
# rotacionar essa chave a qualquer momento — se a busca por CNJ começar a
# falhar com erro de autenticação, confira o valor atual na wiki e defina
# DATAJUD_API_KEY no .env com o valor novo (tem prioridade sobre este default).
DEFAULT_DATAJUD_PUBLIC_API_KEY = 'cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=='


def resolved_datajud_api_key(settings: Settings | None = None) -> str:
    """Ponto único de decisão: DATAJUD_API_KEY do usuário tem prioridade;
    se estiver vazia, cai pra chave pública padrão do CNJ. Nunca espalhar
    esse fallback em outros lugares do código — só aqui."""
    settings = settings or get_settings()
    return settings.datajud_api_key or DEFAULT_DATAJUD_PUBLIC_API_KEY


def datajud_key_source(settings: Settings | None = None) -> str:
    """Pra exibição/diagnóstico: diz se a chave em uso veio do .env do
    usuário ou é a pública padrão — nunca expõe o valor em si."""
    settings = settings or get_settings()
    return 'configurado_pelo_usuario' if settings.datajud_api_key else 'chave_publica_padrao'


def mask_api_key(value: str) -> str:
    """Mascara qualquer chave pra exibição/log: mostra só os 6 primeiros e
    4 últimos caracteres. Nunca usar o valor completo em resposta pública."""
    if not value or len(value) <= 12:
        return '***'
    return f'{value[:6]}...{value[-4:]}'
