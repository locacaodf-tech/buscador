from app.services.precatorio import classify_precatorio


def test_classifica_precatorio_por_classe():
    source = {'classe': {'codigo': 1265, 'nome': 'Precatório'}, 'movimentos': [], 'assuntos': []}
    score, flags = classify_precatorio(source)
    assert score >= 50
    assert 'classe_precatorio_ou_rpv' in flags


def test_classifica_precatorio_pago_reduz_score():
    source = {'classe': {'codigo': 1265, 'nome': 'Precatório'}, 'movimentos': [{'codigo': 12169, 'nome': 'Paga'}], 'assuntos': []}
    score, flags = classify_precatorio(source)
    assert 'consta_movimento_pago' in flags
    assert score > 0
