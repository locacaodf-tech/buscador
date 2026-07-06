"""Runner: decide quais bots acionar pra um dado identificado, executa cada
um (uma falha não derruba os demais), e agrega num resultado único e humano.
Não é uma fila de jobs assíncrona de verdade (este é um FastAPI síncrono,
sem workers em background) — é execução dentro da própria requisição, com
o registro em BotJob/BotStep servindo pra dar visibilidade e permitir
retomar quando um bot específico (o PortalBot) pausa esperando o usuário."""
from __future__ import annotations

from typing import Any

from ..services.identifier import infer_identifier
from .datajud_bot import DataJudBot
from .stj_bot import StjBot
from .precatorio_bot import PrecatorioBot
from .certidao_bot import CertidaoBot

BOT_REGISTRY = {
    'datajud_bot': DataJudBot(),
    'stj_bot': StjBot(),
    'precatorio_bot': PrecatorioBot(),
    'certidao_bot': CertidaoBot(),
}


def bots_status() -> list[dict[str, Any]]:
    """Pra GET /api/bots/status — o que existe e o que cada um faz."""
    from .evidence_bot import EvidenceBot
    from .portal_bot import PortalBot
    todos = list(BOT_REGISTRY.values()) + [EvidenceBot(), PortalBot()]
    return [{'bot_id': b.bot_id, 'nome': b.nome, 'finalidade': b.finalidade} for b in todos]


def calcular_status_job(passos: list[dict[str, Any]]) -> str:
    """Ponto único de verdade sobre o status geral do job — pendência NUNCA
    vira 'completed' (esse foi o bug real da v30: um bot podia reportar
    'pendente' e o job ainda assim ficava 'completed', porque a agregação
    só olhava 'falhou'/'waiting_user', nunca 'pendente').

    Prioridade: waiting_user > failed (tudo falhou) > partial (qualquer
    pendência/falha parcial) > completed (tudo concluído)."""
    if not passos:
        return 'completed'
    status_dos_passos = [p['status'] for p in passos]
    if any(s == 'waiting_user' for s in status_dos_passos):
        return 'waiting_user'
    if all(s == 'falhou' for s in status_dos_passos):
        return 'failed'
    if any(s in {'falhou', 'pendente'} for s in status_dos_passos):
        return 'partial'
    return 'completed'


async def executar_bots(input_texto: str, uf: str | None, tribunal: str | None, objetivo: str) -> dict[str, Any]:
    resolved = infer_identifier(input_texto)
    tipo = resolved.search_type
    valor = resolved.search_key

    passos: list[dict[str, Any]] = []
    resultados_confirmados: list[dict[str, Any]] = []
    indicios: list[dict[str, Any]] = []
    pendencias: list[str] = list(resolved.notes)
    proxima_acao = None

    for bot_id, bot in BOT_REGISTRY.items():
        if not bot.can_run(tipo, objetivo):
            continue
        try:
            resultado = await bot.run(valor=valor, uf=uf, tribunal=tribunal, objetivo=objetivo)
        except Exception as exc:  # uma etapa falhando não derruba as demais
            passos.append({
                'bot_id': bot_id, 'nome': bot.nome, 'status': 'falhou',
                'resultado': {}, 'warnings': [f'Erro inesperado: {exc}'], 'pendencias': [], 'next_action': None,
                'evidence_ids': [], 'session_id': None, 'captcha_image_base64': None,
            })
            continue

        passo_dict = resultado.as_dict()
        evidence_id = _registrar_evidencia_do_bot(bot_id, resultado, tipo, valor)
        if evidence_id:
            passo_dict['evidence_ids'] = [evidence_id]
        passos.append(passo_dict)

        pendencias += resultado.pendencias
        if resultado.resultado.get('resultados_confirmados'):
            resultados_confirmados += resultado.resultado['resultados_confirmados']
        if resultado.resultado.get('indicios'):
            indicios += resultado.resultado['indicios']
        if resultado.next_action and not proxima_acao:
            proxima_acao = resultado.next_action

    # CPF/CNPJ/OAB isolados: sem "bot" dedicado (não há o que executar sem
    # provider comercial), mas a regra de nunca fingir "não encontrado"
    # continua valendo — reaproveita a mesma mensagem do motor.
    if tipo in {'cpf', 'cnpj', 'oab'}:
        from ..services.diligencia_engine import _consultar_pessoa
        parte_pessoa = _consultar_pessoa(tipo, valor)
        passos.append({
            'bot_id': 'pessoa_sem_provider', 'nome': 'Verificação de provider comercial',
            'status': 'pendente', 'resultado': {}, 'warnings': [],
            'pendencias': parte_pessoa['pendencias'], 'next_action': parte_pessoa['proxima_acao'],
            'evidence_ids': [], 'session_id': None, 'captcha_image_base64': None,
        })
        pendencias += parte_pessoa['pendencias']
        proxima_acao = parte_pessoa['proxima_acao']  # prioridade sobre o que outros bots já tenham sugerido

    if not passos:
        proxima_acao = proxima_acao or 'Não identifiquei um bot específico pra este dado. Tente CPF, CNJ, nome, sequencial STJ ou precatório/RPV.'

    status_geral = calcular_status_job(passos)

    # Dedup preservando ordem — mais de um bot pode reportar a mesma pendência
    # (ex.: StjBot e PrecatorioBot ambos avisam "STJ aguardando upload").
    pendencias_sem_duplicata = list(dict.fromkeys(pendencias))

    resumo = f'{len(passos)} bot(s) acionado(s) pra "{input_texto}" (tipo: {tipo}).'

    return {
        'tipo_identificado': tipo,
        'valor_normalizado': valor,
        'status': status_geral,
        'bots_executados': passos,
        'resultados_confirmados': resultados_confirmados,
        'indicios': indicios,
        'pendencias': pendencias_sem_duplicata,
        'proxima_acao_recomendada': proxima_acao or 'Confira os detalhes de cada bot acima.',
        'resumo_humano': resumo,
    }


def _registrar_evidencia_do_bot(bot_id: str, resultado: Any, tipo: str, valor: str) -> int | None:
    """EvidenceBot integrado: cada bot que roda e produz resultado ou
    pendência relevante vira uma evidência automática, vinculada por
    referência ao dado consultado — sem isso, o próprio EvidenceBot nunca
    era chamado de verdade (achado real da auditoria)."""
    from .evidence_bot import registrar_evidencia_automatica

    fontes_e_textos = {
        'datajud_bot': ('DataJud/CNJ', valor, _resumir_resultado(resultado)),
        'stj_bot': ('STJ XLSX', valor, _resumir_resultado(resultado)),
        'precatorio_bot': ('Plano de precatório/RPV', valor, _resumir_resultado(resultado)),
        'certidao_bot': ('Planejamento de certidões', valor, _resumir_resultado(resultado)),
    }
    if bot_id not in fontes_e_textos:
        return None
    fonte, referencia, texto = fontes_e_textos[bot_id]
    if not texto:
        return None
    return registrar_evidencia_automatica(fonte=fonte, referencia=referencia, texto=texto)


def _resumir_resultado(resultado: Any) -> str:
    partes = []
    if resultado.resultado.get('resultados_confirmados'):
        partes.append(f"{len(resultado.resultado['resultados_confirmados'])} resultado(s) confirmado(s).")
    if resultado.pendencias:
        partes.append('Pendências: ' + '; '.join(resultado.pendencias))
    if resultado.warnings:
        partes.append('Avisos: ' + '; '.join(resultado.warnings))
    if resultado.next_action:
        partes.append(f'Próxima ação: {resultado.next_action}')
    return ' '.join(partes)
