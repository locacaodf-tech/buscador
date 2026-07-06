"""CertidaoBot: usa certificate_center pra planejar certidões, sempre em
linguagem humana (nunca nao_integrado, source_mapping_required, captcha_relay.py
ou nome de variável de ambiente — tradutor único em status_em_portugues)."""
from __future__ import annotations

from .base import BaseBot, BotResult
from ..services.certificate_center import build_certificate_plan


class CertidaoBot(BaseBot):
    bot_id = 'certidao_bot'
    nome = 'CertidaoBot'
    finalidade = 'Planejar certidões (cível, criminal, fiscal, trabalhista), separando automático de manual.'

    def can_run(self, tipo_identificado: str, objetivo: str) -> bool:
        return objetivo == 'certidao' or tipo_identificado in {'cpf', 'cnpj'}

    async def run(self, *, valor: str, uf: str | None, tribunal: str | None, objetivo: str) -> BotResult:
        plano = build_certificate_plan(valor, None)
        steps = plano.get('steps', [])

        automaticas = [s for s in steps if s['integration_status'] in {'implemented', 'implemented_partial'}]
        configuraveis = [s for s in steps if s['integration_status'] == 'implemented_configurable']
        manuais = [s for s in steps if s['integration_status'] not in {'implemented', 'implemented_partial', 'implemented_configurable'}]

        pendencias = [f"{s['name']}: {s['status_humano']}" for s in manuais[:5]]
        if automaticas:
            next_action = f'{automaticas[0]["name"]} já responde automaticamente.'
        elif configuraveis:
            next_action = f'{configuraveis[0]["name"]} fica pronta assim que a chave/contrato for configurado.'
        else:
            next_action = 'Nenhuma fonte automática pra este caso ainda — use os links oficiais nas pendências.'

        return BotResult(
            bot_id=self.bot_id, nome=self.nome, status='concluido',
            resultado={'plano': plano, 'automaticas': automaticas, 'configuraveis': configuraveis, 'manuais': manuais},
            pendencias=pendencias,
            next_action=next_action,
        )
