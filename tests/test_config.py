from app.config import parse_allowed_origins


def test_string_vazia_vira_lista_vazia():
    assert parse_allowed_origins('') == []


def test_string_so_espacos_vira_lista_vazia():
    assert parse_allowed_origins('   ') == []


def test_origem_unica():
    assert parse_allowed_origins('https://meu-html.netlify.app') == ['https://meu-html.netlify.app']


def test_multiplas_origens_separadas_por_virgula():
    raw = 'https://a.com,https://b.com,https://c.com'
    assert parse_allowed_origins(raw) == ['https://a.com', 'https://b.com', 'https://c.com']


def test_ignora_espacos_e_virgulas_extras():
    raw = ' https://a.com , https://b.com ,, '
    assert parse_allowed_origins(raw) == ['https://a.com', 'https://b.com']


def test_nunca_retorna_asterisco_implicitamente():
    assert '*' not in parse_allowed_origins('')
    assert '*' not in parse_allowed_origins('https://a.com')
