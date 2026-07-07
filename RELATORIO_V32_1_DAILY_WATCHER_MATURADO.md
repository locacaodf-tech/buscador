# v32.1 — Maturação do Daily Watcher

Confirmei a duplicação antes de corrigir: rodei `/api/watchers/run` duas vezes com o mesmo fixture e vi 12 leads pra 6 processos únicos. Era real.

## 1. Deduplicação — corrigida

Chave de deduplicação: `source + normalized_cnj + signal_type + publication_date + hash do texto`. Rodar o mesmo fixture duas vezes agora:
- 1ª rodada: 6 leads criados.
- 2ª rodada: **0 leads criados, 6 duplicados ignorados** — o lead existente só atualiza `last_seen_at` e soma `seen_count`.

Campos novos: `OpportunityLead.dedupe_key/first_seen_at/last_seen_at/seen_count`, `PublicationHit.text_hash`.

## 2. Bots automáticos — configurável, desligado por padrão

`WATCHERS_AUTO_RUN_BOTS=true/false` (default `false`). Testado nos dois estados:
- **Desligado**: nenhum lead recebe `bot_job_id` automaticamente.
- **Ligado**: só o lead de **prioridade alta** aciona bots sozinho (testado com um lead alta + um lead fraco no mesmo lote — só o alta ganhou `bot_job_id`). Média/baixa continuam manuais mesmo ligado.

`/api/watchers/status` agora mostra isso com todas as letras: *"Bots automáticos desativados — leads de prioridade alta precisam do botão 'Rodar bots'"*.

## 3. Dossiê do lead — criado

`GET /api/leads/{id}/dossie` — funciona **mesmo sem bot_job_id** (testado). Mostra origem, CNJ, tribunal, sinal, score, prioridade, termos batidos, trecho da publicação, status, e se bots já rodaram ou não.

**Achado real testando isso**: o trecho da publicação no dossiê mostrava o CPF sem máscara (o dado cru do fixture). Corrigido reaproveitando a mesma função de mascaramento já testada da v31b (`mascarar_documentos_no_texto`) — testei explicitamente que o CPF não aparece nem em `/api/leads`, nem em `/api/leads/{id}`, nem no dossiê.

## 4. Status geral honesto

`POST /api/watchers/run` agora devolve `{"overall_status": "completed|partial|failed", "watchers": {...}}`. Testado: quando o STJ watcher falha por rede (esperado neste ambiente) e os outros dois completam, `overall_status` vira **`partial`** — nunca esconde que uma fonte falhou.

## 5. Tela

Painel "Robôs diários" agora mostra: status geral traduzido, se bots automáticos estão ligados/desligados (com a frase exata), alternativa de cron gratuita, e duplicados ignorados por watcher. Cada lead ganhou o botão "Abrir dossiê do lead" (funciona sempre) além de "Rodar bots"/"Dossiê dos bots" (quando já rodou).

## 6. Cron externo — documentado objetivamente

`/api/watchers/status.agendamento` agora devolve estruturado: `cron_nativo_ativo: false`, motivo (Render cobra mínimo US$1/mês), alternativa gratuita (cron-job.org), endpoint, método, header necessário, horário sugerido.

## Testes

`pytest -q` → **406 passed** com navegador / **396 passed, 10 skipped** sem navegador. Confirmado do ZIP extraído do zero.

Novo: `tests/test_daily_watcher_maturado.py` (13 testes, cobrindo A-J do pedido). Ajustei 7 testes existentes de `test_daily_watcher.py` pro novo formato de resposta (`overall_status`/`watchers`), mudança deliberada desta rodada.

## O que roda de verdade hoje (sem exagero)

1. **Fixture/lista fornecida** — Publication Watcher, testado e funcionando.
2. **DataJud para CNJs conhecidos** — real, mesmo conector de produção.
3. **STJ watcher** — real, reaproveita o scraper da v30.2.
4. **Cron diário automático** — não existe ainda. Precisa de cron externo gratuito (cron-job.org) apontando pro `POST /api/watchers/run`, documentado no `/api/watchers/status`.
