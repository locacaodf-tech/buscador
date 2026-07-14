# v36 — Fase 1: Multiusuário, Tenant, Postgres/Alembic

## Mapa dos dois repositórios

| Módulo | Decisão |
|---|---|
| Auth (senha única) | **Removido**, substituído por User/Tenant/UserSession real |
| Stack de banco (SQLite) | **Preservado como dev/teste**; produção passa a usar `DATABASE_URL` Postgres via Alembic |
| Domínio do Buscador (CNJ, precatório, STJ, leads) | **Preservado integralmente**, agora com acesso controlado por permissão |
| Modelos do BuyerRadar (organizations/funds/people/contacts/buyer_profiles/mandates/campaigns/etc.) | **Trazidos como schema**, adaptados pra minha Base/tenant — motor de negócio (matching/scoring/envio) é Fase 2+ |
| Endpoint `/api/auth/register` do BuyerRadar | **Não trazido** — vulnerabilidade confirmada (público, aceitava `role` arbitrária); substituído por bootstrap CLI + criação admin-only |
| Frontend Next.js do BuyerRadar | Não avaliado nesta rodada — Fase 1 focou em fundação de dados, não UI |

## O que foi entregue de verdade

- **Tenant/User/UserSession/AuditLogEntry** — sessão revogável de verdade (token opaco + hash, não JWT sem estado), não só um "papel" solto no banco.
- **6 papéis com permissões efetivas**, checadas em cada rota nova (`PERMISSOES_POR_PAPEL`, testado que nenhum papel tem os mesmos privilégios do administrador).
- **Nenhum usuário altera o próprio papel** — nem administrador. Testado.
- **Bootstrap seguro**: `python cli.py bootstrap-admin` — primeiro admin só nasce assim, nunca por endpoint público.
- **Alembic configurado de verdade**, migration inicial gerada e testada do zero (33 tabelas). `DATABASE_URL` já era abstraído no engine — só precisava do Postgres driver (`psycopg2-binary`) e do Alembic por cima.
- **Schema do BuyerRadar trazido**: Organization, Fund, BuyerProfile, BuyerMandate, Person, Contact, JudicialOpportunity (entidade central pedida), OpportunityFieldSource (fonte/confiança por campo, "nunca tratar inferência como fato"), BuyerAssetMatch, Campaign, CampaignRecipient, OutboundMessage (com `idempotency_key` único — corrigindo o achado de "idempotência inadequada"), SuppressionEntry, Proposal (nova).
- **Script de migração** `python cli.py migrate-buyerradar --source <url> --dry-run` — testado com origem simulada: detecta tabelas, conta registros, identifica duplicados por chave única, só grava com `--no-dry-run` explícito.
- **`CAMPAIGN_SENDING_ENABLED=false`** — a trava técnica pedida pro envio real de campanha, pronta pra Fase 5.

## Achado real corrigido no caminho

Testando o fluxo de sessão, achei um bug de `datetime` (comparar horário com/sem fuso horário quebrava toda verificação de sessão) e uma armadilha real de teste (criar usuário "vazando" entre arquivos de teste porque o banco é compartilhado — resolvido com `conftest.py` limpando o estado antes de cada teste, evitando que 29 testes não relacionados a auth quebrassem em cascata).

## Testes

443 passed (433+10 sem navegador). Confirmado do ZIP extraído do zero, incluindo `alembic upgrade head` + `bootstrap-admin` rodando de verdade antes da suíte.

## Pendências explícitas para a Fase 2

- Motor de matching/scoring (score 0-100, cobertura de dados) — não implementado.
- Conversão de processo em ativo ("Analisar como ativo judicial") — não implementado.
- Geração de teaser, campanhas, disparo — estrutura de dados pronta, lógica de negócio não implementada.
- Robôs de descoberta de compradores (CVM, sites institucionais) — não implementado.
- Avaliação do frontend Next.js do BuyerRadar — não feita nesta rodada.
- Per-endpoint: a permissão granular está implementada e testada nos endpoints NOVOS (admin); os endpoints JÁ EXISTENTES do Buscador continuam exigindo só "estar logado" (qualquer papel), sem checagem granular por recurso ainda — isso é trabalho de Fase 2, não childs desta rodada.
