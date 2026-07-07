"""v32 — LeadRanker: pontua uma oportunidade de 0 a 100, com regras
explícitas e testáveis — nunca uma pontuação "por vibe". Score alto =
alta prioridade; nada aqui decide sozinho, só ordena o que merece
atenção primeiro."""
from __future__ import annotations

from typing import Any

PONTOS_POSITIVOS = {
    'tem_precatorio_rpv_oficio': 25,
    'tem_ente_devedor_publico': 15,
    'natureza_alimentar': 15,
    'tem_valor_explicito': 10,
    'cnj_valido': 15,
    'tribunal_inferido': 10,
    'transito_calculo_homologacao': 10,
}

PONTOS_NEGATIVOS = {
    'segredo_de_justica': -40,
    'sem_cnj': -20,
    'publicacao_generica': -20,
    'embargos_recurso_rescisoria': -15,
}

SIGNAL_TYPES_ALTA_PRIORIDADE = {'precatorio_confirmado', 'rpv_confirmada', 'oficio_requisitorio'}
SIGNAL_TYPES_MEDIA_PRIORIDADE = {'pre_rpv', 'pre_precatorio', 'calculo_homologado', 'transito_em_julgado', 'cumprimento_sentenca', 'sentenca_favoravel', 'acordao_favoravel', 'credito_judicial_potencial'}


def calcular_score(*, signal_type: str | None, cnj: str | None, tribunal: str | None,
                    ente_devedor: str | None, natureza_alimentar: bool, valor_explicito: bool,
                    segredo_de_justica: bool, termos_negativos: list[str]) -> dict[str, Any]:
    """Calcula o score final e a prioridade — cada ponto ganho/perdido é
    rastreável (fica em 'motivos'), não uma caixa preta."""
    score = 0
    motivos = []

    if signal_type in SIGNAL_TYPES_ALTA_PRIORIDADE:
        score += PONTOS_POSITIVOS['tem_precatorio_rpv_oficio']
        motivos.append(f"+{PONTOS_POSITIVOS['tem_precatorio_rpv_oficio']}: sinal de alta prioridade ({signal_type})")
    elif signal_type in SIGNAL_TYPES_MEDIA_PRIORIDADE:
        score += PONTOS_POSITIVOS['transito_calculo_homologacao']
        motivos.append(f"+{PONTOS_POSITIVOS['transito_calculo_homologacao']}: sinal de pré-oportunidade ({signal_type})")

    if ente_devedor:
        score += PONTOS_POSITIVOS['tem_ente_devedor_publico']
        motivos.append(f"+{PONTOS_POSITIVOS['tem_ente_devedor_publico']}: ente devedor público ({ente_devedor})")

    if natureza_alimentar:
        score += PONTOS_POSITIVOS['natureza_alimentar']
        motivos.append(f"+{PONTOS_POSITIVOS['natureza_alimentar']}: natureza alimentar")

    if valor_explicito:
        score += PONTOS_POSITIVOS['tem_valor_explicito']
        motivos.append(f"+{PONTOS_POSITIVOS['tem_valor_explicito']}: valor explícito na publicação")

    if cnj:
        score += PONTOS_POSITIVOS['cnj_valido']
        motivos.append(f"+{PONTOS_POSITIVOS['cnj_valido']}: CNJ válido identificado")
    else:
        score += PONTOS_NEGATIVOS['sem_cnj']
        motivos.append(f"{PONTOS_NEGATIVOS['sem_cnj']}: sem CNJ identificável")

    if tribunal:
        score += PONTOS_POSITIVOS['tribunal_inferido']
        motivos.append(f"+{PONTOS_POSITIVOS['tribunal_inferido']}: tribunal inferido ({tribunal})")

    if segredo_de_justica:
        score += PONTOS_NEGATIVOS['segredo_de_justica']
        motivos.append(f"{PONTOS_NEGATIVOS['segredo_de_justica']}: segredo de justiça")

    if not signal_type or signal_type in {'lead_fraco', 'descartar'}:
        score += PONTOS_NEGATIVOS['publicacao_generica']
        motivos.append(f"{PONTOS_NEGATIVOS['publicacao_generica']}: publicação genérica/sem sinal claro")

    if termos_negativos:
        score += PONTOS_NEGATIVOS['embargos_recurso_rescisoria']
        motivos.append(f"{PONTOS_NEGATIVOS['embargos_recurso_rescisoria']}: contém {', '.join(termos_negativos)} (pode atrasar pagamento)")

    score = max(0, min(100, score))

    if score >= 60:
        prioridade = 'alta'
    elif score >= 30:
        prioridade = 'media'
    else:
        prioridade = 'baixa'

    return {'score': score, 'prioridade': prioridade, 'motivos': motivos}
