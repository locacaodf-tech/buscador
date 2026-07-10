"""v32 — Motor de sinais: classifica um texto de publicação/movimentação em
um signal_type (precatório confirmado, pré-RPV, trabalhista, etc.), extrai
CNJ/ente devedor/natureza — reaproveita o mesmo estilo de detecção por
palavra-chave já usado no whatsapp_intake.py (não duplica, mas segue o
mesmo padrão comprovado: marcador textual claro, nunca um palpite)."""
from __future__ import annotations

import re
from typing import Any

# Termos por categoria, na ordem de prioridade de classificação (mais
# específico primeiro). Cada tupla é (termo, signal_type).
SINAIS_ALTA_PRIORIDADE = [
    ('ofício requisitório', 'oficio_requisitorio'), ('oficio requisitorio', 'oficio_requisitorio'),
    ('expedição de precatório', 'precatorio_confirmado'), ('expedicao de precatorio', 'precatorio_confirmado'),
    ('expedição de rpv', 'rpv_confirmada'), ('expedicao de rpv', 'rpv_confirmada'),
    ('requisição de pequeno valor', 'rpv_confirmada'), ('requisicao de pequeno valor', 'rpv_confirmada'),
    ('inclusão em proposta orçamentária', 'precatorio_confirmado'), ('inclusao em proposta orcamentaria', 'precatorio_confirmado'),
    ('depre', 'precatorio_confirmado'),
    ('rpv', 'rpv_confirmada'),
    ('precatório', 'precatorio_confirmado'), ('precatorio', 'precatorio_confirmado'),
    ('requisitório', 'oficio_requisitorio'), ('requisitorio', 'oficio_requisitorio'),
]

SINAIS_PRE_RPV_PRECATORIO = [
    ('homologo os cálculos', 'calculo_homologado'), ('homologo os calculos', 'calculo_homologado'),
    ('cálculos homologados', 'calculo_homologado'), ('calculos homologados', 'calculo_homologado'),
    ('cálculo de liquidação', 'calculo_homologado'), ('calculo de liquidacao', 'calculo_homologado'),
    ('secaj', 'calculo_homologado'),  # setor de cálculos judiciais — pedido explícito do usuário
    ('liquidação de sentença', 'cumprimento_sentenca'), ('liquidacao de sentenca', 'cumprimento_sentenca'),
    ('certidão de trânsito', 'transito_em_julgado'), ('certidao de transito', 'transito_em_julgado'),
    ('trânsito em julgado', 'transito_em_julgado'), ('transito em julgado', 'transito_em_julgado'),
    ('cumprimento de sentença', 'cumprimento_sentenca'), ('cumprimento de sentenca', 'cumprimento_sentenca'),
    ('intime-se para pagamento', 'pre_rpv'),
    ('julgo procedente', 'sentenca_proferida'), ('sentença', 'sentenca_proferida'), ('sentenca', 'sentenca_proferida'),
]

SINAIS_TRABALHISTA = [
    ('precatório trabalhista', 'precatorio_confirmado'), ('precatorio trabalhista', 'precatorio_confirmado'),
    ('reintegração', 'sentenca_favoravel'), ('reintegracao', 'sentenca_favoravel'),
    ('anistia', 'sentenca_favoravel'),
    ('diferenças salariais', 'sentenca_favoravel'), ('diferencas salariais', 'sentenca_favoravel'),
    ('verbas vencidas', 'sentenca_favoravel'),
    ('horas extras', 'credito_judicial_potencial'),
    ('servidor público', 'credito_judicial_potencial'), ('servidor publico', 'credito_judicial_potencial'),
    ('quinquênio', 'credito_judicial_potencial'), ('quinquenio', 'credito_judicial_potencial'),
    ('adicional', 'credito_judicial_potencial'),
    ('progressão', 'credito_judicial_potencial'), ('progressao', 'credito_judicial_potencial'),
    ('retroativo', 'credito_judicial_potencial'),
]

ENTES_DEVEDORES = ['INSS', 'União', 'Fazenda Pública', 'Fazenda Nacional', 'Estado de', 'Município de', 'Governo do Estado']

TERMOS_QUE_REDUZEM_SCORE = [
    ('segredo de justiça', -30), ('segredo de justica', -30),
    ('embargos', -10), ('agravo', -5), ('recurso', -5), ('rescisória', -10), ('rescisoria', -10),
]


def _remover_acentos(texto: str) -> str:
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')


def classificar_publicacao(texto: str) -> dict[str, Any]:
    """Ponto único de classificação: devolve signal_type, termos batidos,
    ente devedor e natureza (se identificável). Nunca inventa — se nada
    bater, signal_type vira 'lead_fraco' ou 'descartar'."""
    texto_norm = _remover_acentos(texto.lower())
    termos_batidos = []
    signal_type = None

    for grupo in (SINAIS_ALTA_PRIORIDADE, SINAIS_PRE_RPV_PRECATORIO, SINAIS_TRABALHISTA):
        for termo, tipo in grupo:
            if _remover_acentos(termo) in texto_norm:
                termos_batidos.append(termo)
                if signal_type is None:
                    signal_type = tipo

    ente_devedor = None
    for ente in ENTES_DEVEDORES:
        if _remover_acentos(ente.lower()) in texto_norm:
            ente_devedor = ente
            break
    if ente_devedor:
        # v33: achado real — ENTES_DEVEDORES aqui tinha o MESMO bug já
        # corrigido em whatsapp_intake.extrair_ente_devedor (devolvia só
        # "Estado de", cortado, em vez de "Estado de Goiás" completo).
        # Reaproveita a versão já corrigida, sem duplicar a lógica de novo.
        from ..services.whatsapp_intake import extrair_ente_devedor
        ente_completo = extrair_ente_devedor(texto)
        if ente_completo:
            ente_devedor = ente_completo

    natureza_alimentar = 'alimentar' in texto_norm

    if not termos_batidos:
        signal_type = 'descartar' if len(texto.strip()) < 20 else 'lead_fraco'

    return {
        'signal_type': signal_type,
        'termos_batidos': termos_batidos,
        'ente_devedor': ente_devedor,
        'natureza_alimentar': natureza_alimentar,
    }
