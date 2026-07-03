import time

from app.auth import create_session_token, verify_session_token


SECRET = 'segredo-de-teste'


def test_token_valido_recem_criado():
    token = create_session_token(SECRET)
    assert verify_session_token(token, SECRET) is True


def test_token_rejeita_segredo_errado():
    token = create_session_token(SECRET)
    assert verify_session_token(token, 'outro-segredo') is False


def test_token_expirado_e_invalido():
    token = create_session_token(SECRET, ttl_seconds=-10)
    assert verify_session_token(token, SECRET) is False


def test_token_none_e_invalido():
    assert verify_session_token(None, SECRET) is False


def test_token_malformado_e_invalido():
    assert verify_session_token('qualquer-coisa-sem-ponto', SECRET) is False
    assert verify_session_token('abc.def', SECRET) is False


def test_token_adulterado_e_invalido():
    token = create_session_token(SECRET)
    expires_at, _, signature = token.partition('.')
    # troca a expiração mas mantém a assinatura antiga
    adulterado = f'{int(expires_at) + 999999}.{signature}'
    assert verify_session_token(adulterado, SECRET) is False


def test_token_respeita_ttl_customizado():
    token = create_session_token(SECRET, ttl_seconds=1)
    assert verify_session_token(token, SECRET) is True
    time.sleep(1.2)
    assert verify_session_token(token, SECRET) is False
