"""IntakeBot: aciona os bots existentes com base no que foi extraído da
mensagem de WhatsApp — se achou CNJ, aciona DataJudBot/StjBot/PrecatorioBot
normalmente (mesmo runner de sempre, reaproveitado, não duplicado)."""
from __future__ import annotations

from typing import Any


async def acionar_bots_para_caso(dados_extraidos: dict[str, Any], db: Any = None) -> dict[str, Any] | None:
    """Se o texto trouxe um processo/CNJ reconhecível, aciona os bots
    normais (mesmo /api/bots/run por baixo) usando o CNJ como entrada.
    Sem processo detectado, não aciona nada — não força um bot rodar sem
    ter o que consultar."""
    processos = dados_extraidos.get('processos_detectados') or []
    if not processos:
        return None

    from .runner import executar_bots
    cnj = processos[0]['cnj_normalizado']
    return await executar_bots(cnj, None, processos[0].get('tribunal_provavel'), 'completo', db=db)
