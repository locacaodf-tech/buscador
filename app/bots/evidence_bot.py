"""EvidenceBot: salva evidência (automática, vinda de outro bot, ou manual)
vinculada a uma diligência/job. Reaproveita o modelo ManualEvidence e o
serviço manual_evidence.py já existentes — não cria um segundo mecanismo
de guardar arquivo."""
from __future__ import annotations

from .base import BaseBot, BotResult
from ..db import SessionLocal
from ..models import ManualEvidence


class EvidenceBot(BaseBot):
    bot_id = 'evidence_bot'
    nome = 'EvidenceBot'
    finalidade = 'Salvar evidência (fonte, texto, arquivo) vinculada à diligência.'

    def can_run(self, tipo_identificado: str, objetivo: str) -> bool:
        return False  # não é acionado automaticamente pelo runner — só via registrar_evidencia_automatica()

    async def run(self, *, valor: str, uf: str | None, tribunal: str | None, objetivo: str) -> BotResult:
        return BotResult(bot_id=self.bot_id, nome=self.nome, status='concluido', next_action='Nenhuma ação — use registrar_evidencia_automatica().')


def registrar_evidencia_automatica(*, fonte: str, referencia: str, texto: str) -> int:
    """Salva uma evidência gerada automaticamente por outro bot (ex.: o
    HTML capturado pelo PortalBot depois de uma consulta bem-sucedida).
    Devolve o id do registro salvo."""
    db = SessionLocal()
    try:
        registro = ManualEvidence(fonte=fonte, referencia=referencia, texto=texto)
        db.add(registro)
        db.commit()
        db.refresh(registro)
        return registro.id
    finally:
        db.close()
