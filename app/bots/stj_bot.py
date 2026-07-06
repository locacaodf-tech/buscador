"""StjBot: aciona a busca nos arquivos oficiais do STJ (sequencial, processo
ou nome). Reaproveita _consultar_stj do motor — a MESMA checagem de "há
XLSX carregado?" usada em todo o resto do sistema, sem duplicar."""
from __future__ import annotations

from .base import BaseBot, BotResult
from ..services import diligencia_engine, stj_uploads


class StjBot(BaseBot):
    bot_id = 'stj_bot'
    nome = 'StjBot'
    finalidade = 'Buscar sequencial, processo ou nome nos arquivos oficiais do STJ já carregados.'

    def can_run(self, tipo_identificado: str, objetivo: str) -> bool:
        return tipo_identificado in {'name', 'unknown', 'sequencial', 'precatorio_number', 'rpv_number', 'requisitorio_number'}

    async def run(self, *, valor: str, uf: str | None, tribunal: str | None, objetivo: str) -> BotResult:
        if not stj_uploads.has_uploaded_file():
            return BotResult(
                bot_id=self.bot_id, nome=self.nome, status='pendente',
                pendencias=['STJ aguardando upload do XLSX oficial.'],
                next_action='Carregue o XLSX oficial do STJ para destravar a consulta automática.',
            )

        tipo_busca = 'name' if valor and not valor.replace('.', '').isdigit() else 'sequencial'
        parte = diligencia_engine._consultar_stj(tipo_busca, valor)
        resultados = parte.get('resultados_confirmados', [])
        status = 'concluido' if resultados else ('concluido' if not parte.get('pendencias') else 'pendente')

        return BotResult(
            bot_id=self.bot_id, nome=self.nome, status=status,
            resultado={'resultados_confirmados': resultados},
            pendencias=parte.get('pendencias', []),
            next_action=parte.get('proxima_acao'),
        )
