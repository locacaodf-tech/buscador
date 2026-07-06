"""StjBot: aciona a busca nos arquivos oficiais do STJ (sequencial, processo
ou nome). Reaproveita _consultar_stj do motor — a MESMA checagem de "há
XLSX carregado?" usada em todo o resto do sistema, sem duplicar.

v30.2: antes de simplesmente pedir upload manual, tenta baixar os arquivos
oficiais direto da página pública do STJ (stj_official_scraper). Só cai
pra "aguardando upload manual" se a tentativa de download genuinamente
falhar — nunca mais "abrir o link oficial" como se fosse a execução em si."""
from __future__ import annotations

from typing import Any

from .base import BaseBot, BotResult
from ..services import diligencia_engine, stj_uploads


class StjBot(BaseBot):
    bot_id = 'stj_bot'
    nome = 'StjBot'
    finalidade = 'Buscar sequencial, processo ou nome nos arquivos oficiais do STJ — baixando automaticamente da página pública quando necessário.'

    def can_run(self, tipo_identificado: str, objetivo: str) -> bool:
        return tipo_identificado in {'name', 'unknown', 'sequencial', 'precatorio_number', 'rpv_number', 'requisitorio_number'}

    async def run(self, *, valor: str, uf: str | None, tribunal: str | None, objetivo: str, db: Any = None) -> BotResult:
        tipo_busca = 'name' if valor and not valor.replace('.', '').isdigit() else 'sequencial'

        if not stj_uploads.has_uploaded_file():
            if db is None:
                # Sem sessão de banco disponível, não dá pra sincronizar nem
                # registrar StjOfficialFile — cai no pedido de upload manual,
                # honesto sobre a limitação, não uma falha silenciosa.
                return BotResult(
                    bot_id=self.bot_id, nome=self.nome, status='pendente',
                    pendencias=['STJ aguardando upload do XLSX oficial.'],
                    next_action='Carregue o XLSX oficial do STJ para destravar a consulta automática.',
                )
            from ..services.stj_official_scraper import sync_official_files, registros_de_arquivos_baixados
            sync_resultado = await sync_official_files(db)
            if sync_resultado['status'] != 'ok':
                motivo = {
                    'falhou_acessar_pagina': f"Não consegui acessar a página oficial do STJ agora ({sync_resultado.get('erro_pagina')}).",
                    'nenhum_arquivo_encontrado': 'A página oficial do STJ não trouxe nenhum arquivo XLSX/CSV encontrável agora.',
                    'falhou_baixar_todos': 'Encontrei arquivos na página oficial do STJ, mas não consegui baixar nenhum agora.',
                }.get(sync_resultado['status'], 'Não consegui sincronizar os arquivos oficiais do STJ agora.')
                return BotResult(
                    bot_id=self.bot_id, nome=self.nome, status='pendente',
                    resultado={'tentativa_sync': sync_resultado},
                    # Mantém a frase estável "STJ aguardando upload do XLSX
                    # oficial" em toda variação — é o marcador que o resto do
                    # sistema (e os próprios testes) usa pra reconhecer essa
                    # pendência, independente do motivo detalhado do dia.
                    pendencias=[f'STJ aguardando upload do XLSX oficial. {motivo} Envie o arquivo manualmente.'],
                    next_action='StjBot precisa de upload manual do XLSX — a tentativa automática de baixar da página oficial não funcionou agora.',
                )
            # Sincronizou com sucesso — busca já nos dados recém-baixados,
            # sem precisar que o usuário carregue nada.
            registros = registros_de_arquivos_baixados(db)
            from ..connectors.stj_precatorios import match_records, normalizar_registro_para_exibicao
            brutos = match_records(registros, tipo_busca, valor)
            # Mesma normalização de campos que _consultar_stj usa pro fluxo
            # manual — sem isso, o dossiê e a tela recebiam nomes de campo
            # diferentes conforme o dado veio de upload manual ou sync
            # automático (achado real testando o dossiê).
            encontrados = [normalizar_registro_para_exibicao(r, fonte_padrao='STJ - baixado automaticamente da página oficial') for r in brutos]
            status = 'concluido'
            return BotResult(
                bot_id=self.bot_id, nome=self.nome, status=status,
                resultado={'resultados_confirmados': encontrados, 'tentativa_sync': sync_resultado},
                next_action='StjBot baixou os arquivos oficiais automaticamente e já buscou o dado.' if encontrados else 'StjBot baixou os arquivos oficiais automaticamente, mas não encontrou esse dado neles.',
            )

        parte = diligencia_engine._consultar_stj(tipo_busca, valor)
        resultados = parte.get('resultados_confirmados', [])
        status = 'concluido' if resultados else ('concluido' if not parte.get('pendencias') else 'pendente')

        return BotResult(
            bot_id=self.bot_id, nome=self.nome, status=status,
            resultado={'resultados_confirmados': resultados},
            pendencias=parte.get('pendencias', []),
            next_action=parte.get('proxima_acao'),
        )
