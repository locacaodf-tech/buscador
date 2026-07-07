# v32 — Daily Watcher + Consolidação v31g

## Fase 1 — Consolidação (feita antes de qualquer código novo)

Rodei a suíte completa como linha de base (374 passed) e revalidei os 5 casos específicos direto na função central (`infer_identifier`):

| Caso | Tribunal esperado | Resultado |
|---|---|---|
| TJSP com sufixo `/01` | TJSP | ✅ tipo=cnj, sufixo=01 |
| TJBA ação rescisória | TJBA | ✅ |
| TRF3 | TRF3 | ✅ |
| TJPE | TJPE | ✅ |
| TJAL | TJAL | ✅ |

Nenhuma regressão encontrada — a v31g está sólida. Segui pra Fase 2.

## Fase 2 — Daily Watcher

### Pesquisa feita antes de construir (não presumi nada)

**DJEN (Diário de Justiça Eletrônico Nacional)**: pesquisei se existe uma API pública de consulta (não só a de envio, que já sabia exigir credencial institucional). Achado: existe uma API de consulta documentada (`docs.pdpj.jus.br`, sistema "Domicílio Judicial Eletrônico"), mas ela **exige cabeçalho `tenantId` vinculado a conta institucional/advocatícia** — não é busca pública aberta por palavra-chave sem esse vínculo. Não encontrei uma forma de consultar publicações nacionalmente sem essa credencial.

**Render cron jobs**: pesquisei e confirmei — **cron jobs não têm tier gratuito no Render** (mínimo $1/mês). O free tier deste projeto não suporta agendamento nativo.

### O que isso significa na prática, com honestidade

- **Publication Watcher**: funciona de verdade — classifica, pontua e gera lead pra qualquer lista de publicações que você fornecer. Sem uma fonte pública aberta confirmada, ele roda com um **fixture de demonstração embutido** (`app/watchers/sample_data/publicacoes_exemplo.json`) que prova a esteira inteira: publicação → sinal → lead → bots → dossiê. Se você (ou sua esposa, com acesso profissional) tiver uma conta com acesso ao Domicílio Judicial Eletrônico, dá pra plugar isso sem mudar mais nada — a função `processar_publicacoes()` já aceita qualquer lista de publicações reais.
- **DataJud Movement Watcher**: **real**. Revarre CNJs já conhecidos no DataJud de verdade (mesmo conector já testado em produção) procurando movimentação nova.
- **STJ Official File Watcher**: **real**. Reaproveita o scraper da v30.2 (que já baixa e processa arquivos oficiais de verdade).
- **Agendamento diário**: nenhum cron ativo agora. `POST /api/watchers/run` funciona manualmente. Pra automatizar de verdade sem custo, a opção real é um cron externo gratuito (ex.: `cron-job.org`) apontando pra esse endpoint uma vez por dia — documentado no endpoint `/api/watchers/status`.

## O que foi criado

- `app/watchers/` — `base.py`, `scheduler.py`, `publication_watcher.py`, `datajud_movement_watcher.py`, `stj_official_file_watcher.py`, `precatorio_signal_engine.py`, `lead_ranker.py`.
- `WatcherRun`, `PublicationHit`, `OpportunityLead` (modelos novos).
- 9 endpoints: `GET/POST /api/watchers/*`, `GET /api/leads`, `GET /api/leads/{id}`, `POST /api/leads/{id}/run-bots`, `.../dismiss`, `.../mark-contacted`.
- Tela "Leads encontrados" + "Robôs diários" — rodar manualmente, ver score/prioridade, abrir dossiê, marcar contatado, descartar.
- `tests/test_daily_watcher.py` (19 testes).

## Preservado integralmente

IntakeBot, DataJudBot, StjBot, PrecatorioBot, CertidaoBot, EvidenceBot, PortalBot, BotJob/BotStep, diligência, dossiês, histórico, upload STJ, diagnóstico — nada removido, nada quebrado (confirmado pela suíte completa).

## Testes

`pytest -q` → **393 passed** com navegador / **383 passed, 10 skipped** sem navegador. Confirmado do ZIP extraído do zero.

## Definição de pronto — checklist

1. ✅ v31g continua funcionando (suíte completa + 5 casos revalidados).
2. ✅ CNJ com `/01` funciona globalmente (já era a v31g).
3. ✅ Ação rescisória/processo referência continua funcionando.
4. ✅ Watcher manual roda (`POST /api/watchers/run`).
5. ✅ Fixture de publicação gera lead.
6. ✅ Lead aparece na tela.
7. ✅ Lead aciona bots.
8. ✅ Dossiê do lead abre.
9. ✅ STJ watcher funciona (ou gera pendência clara — testado nos dois casos).
10. ✅ Preparado pra agendamento diário (endpoint pronto + cron externo documentado).
11. ✅ Não prometo cobertura que não existe — DJEN nacional real fica pendente de credencial institucional, dito com todas as letras.
