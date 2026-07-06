"""DataJudBot: aciona a consulta ao DataJud pra CNJ/número de processo.
Reaproveita _consultar_cnj do motor de diligência — não duplica a lógica de
inferência de tribunal nem o tratamento das 3 situações (inválido/sem
resultado/falhou), que já foram corrigidas ali."""
from __future__ import annotations

from .base import BaseBot, BotResult
from ..services import diligencia_engine


class DataJudBot(BaseBot):
    bot_id = 'datajud_bot'
    nome = 'DataJudBot'
    finalidade = 'Consultar processo por CNJ na API pública do DataJud/CNJ.'

    def can_run(self, tipo_identificado: str, objetivo: str) -> bool:
        return tipo_identificado in {'cnj', 'numero_processo'}

    async def run(self, *, valor: str, uf: str | None, tribunal: str | None, objetivo: str) -> BotResult:
        parte = await diligencia_engine._consultar_cnj(valor, tribunal)
        consulta = (parte.get('raw') or {}).get('consulta', {})
        status_consulta = consulta.get('status_consulta')
        status_bot = {
            'encontrado': 'concluido',
            'consultado_sem_resultado': 'concluido',
            'falhou': 'falhou',
        }.get(status_consulta, 'concluido')

        warnings = []
        if status_bot == 'falhou':
            warnings.append('DataJud não respondeu — falha de rede/API, não erro de dado.')

        return BotResult(
            bot_id=self.bot_id, nome=self.nome, status=status_bot,
            resultado={
                'resultados_confirmados': parte.get('resultados_confirmados', []),
                'indicios': parte.get('indicios', []),
                'consulta': consulta,
            },
            warnings=warnings,
            pendencias=parte.get('pendencias', []),
            next_action=parte.get('proxima_acao'),
        )
