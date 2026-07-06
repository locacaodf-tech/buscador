"""Interface comum de todos os bots executores (v30). Cada bot é uma função
fina que ORQUESTRA serviços que já existem e funcionam (diligencia_engine,
stj_uploads, certificate_center, captcha_relay) — nenhum bot reimplementa
lógica que já está em produção. Isso é deliberado: o hotfix anterior mostrou
o preço real de duplicar a mesma regra em dois lugares (o mesmo bug de "STJ
automático sem XLSX" apareceu tanto no motor quanto no endpoint de plano).
Bots aqui são wrappers finos com rastreamento de execução, não uma segunda
implementação da mesma inteligência.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BotResult:
    """Resultado padronizado de qualquer bot. status é sempre um destes:
    'concluido' | 'falhou' | 'pendente' | 'waiting_user'."""
    bot_id: str
    nome: str
    status: str
    resultado: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    pendencias: list[str] = field(default_factory=list)
    evidence_ids: list[int] = field(default_factory=list)
    next_action: str | None = None
    # Preenchido só quando status == 'waiting_user' (ex.: PortalBot pausado
    # num captcha) — id da sessão de navegador que /resume vai retomar.
    session_id: str | None = None
    captcha_image_base64: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            'bot_id': self.bot_id,
            'nome': self.nome,
            'status': self.status,
            'resultado': self.resultado,
            'warnings': self.warnings,
            'pendencias': self.pendencias,
            'evidence_ids': self.evidence_ids,
            'next_action': self.next_action,
            'session_id': self.session_id,
            'captcha_image_base64': self.captcha_image_base64,
        }


class BaseBot:
    """Todo bot tem essa forma: id, nome, finalidade, e um run() assíncrono
    que devolve um BotResult. can_run() decide se esse bot deveria ser
    acionado pra um determinado tipo de dado identificado — o runner usa
    isso pra montar a lista de bots relevantes pra cada diligência."""
    bot_id: str = 'base'
    nome: str = 'Bot base'
    finalidade: str = ''

    def can_run(self, tipo_identificado: str, objetivo: str) -> bool:
        raise NotImplementedError

    async def run(self, *, valor: str, uf: str | None, tribunal: str | None, objetivo: str, db: Any = None) -> BotResult:
        raise NotImplementedError
