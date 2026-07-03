from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_env: str = 'local'
    app_secret: str = 'troque-esta-chave'
    database_url: str = 'sqlite:///./buscador_processos.db'

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
    # Origens (domínios) autorizadas por CORS a chamar a API a partir de um
    # frontend publicado separadamente (ex.: HTML estático no Netlify/Vercel).
    # Múltiplas origens separadas por vírgula. Vazio = nenhuma origem cross-origin liberada.
    frontend_allowed_origins: str = ''
    # Pasta local com XLSX do STJ baixados manualmente (modo offline do
    # conector stj_precatorios). Vazio = modo online (baixa da página oficial).
    stj_local_dir: str = ''
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
