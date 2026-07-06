"""PrecatorioBot: gera o plano operacional de precatório/RPV/requisitório.
Reaproveita _consultar_precatorio do motor — inclui a correção mais recente
(STJ só conta como "pronto" se o XLSX estiver de fato carregado)."""
from __future__ import annotations

from .base import BaseBot, BotResult
from ..services import diligencia_engine


class PrecatorioBot(BaseBot):
    bot_id = 'precatorio_bot'
    nome = 'PrecatorioBot'
    finalidade = 'Gerar plano operacional de busca de precatório/RPV/requisitório.'

    def can_run(self, tipo_identificado: str, objetivo: str) -> bool:
        return tipo_identificado in {'precatorio_number', 'rpv_number', 'requisitorio_number', 'unknown'} or objetivo == 'precatorio'

    async def run(self, *, valor: str, uf: str | None, tribunal: str | None, objetivo: str) -> BotResult:
        tipo = 'precatorio_number'
        parte = diligencia_engine._consultar_precatorio(tipo, valor, uf, tribunal)
        plano = parte.get('raw', {})
        candidatos = plano.get('candidate_sources') or []
        status = 'concluido' if candidatos else 'pendente'

        return BotResult(
            bot_id=self.bot_id, nome=self.nome, status=status,
            resultado={'plano': plano},
            pendencias=parte.get('pendencias', []),
            next_action=parte.get('proxima_acao'),
        )
