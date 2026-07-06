# v30 — Bots Executores de Diligência

Preservei tudo: DataJud, STJ XLSX, /api/diligencia, diligencia_engine.py, histórico, dossiê, evidências, certidões, diagnóstico, login, Render/Docker, testes. Nada foi apagado. `/api/diligencia` continua funcionando exatamente como antes (testado).

## Achado importante antes de construir — leia isto primeiro

O registro interno do TJPE dizia "MELHOR ALVO REAL PARA O captcha_relay.py". Antes de usar esse alvo, checei o `robots.txt` de `certidoesunificadas.app.tjpe.jus.br` — **ele proíbe explicitamente acesso automatizado**. Isso descarta o TJPE como alvo do PortalBot: usá-lo violaria a regra permanente deste projeto ("robots.txt é linha vermelha"), então não implementei automação contra ele, mesmo a nota antiga sugerindo isso.

Testei uma alternativa: `processual.trf1.jus.br` (consulta processual do TRF1) **não é bloqueado** por robots.txt. Mas o sandbox onde isso foi desenvolvido só alcança GitHub/PyPI/npm — não consegui abrir esse portal real pra inspecionar o HTML e extrair os seletores exatos dos campos do formulário. Não inventei seletores: um bot que "parece funcionar" com seletor errado é pior que ser honesto sobre essa lacuna.

**O que isso significa na prática**: o mecanismo do PortalBot é real, testado, e funciona de ponta a ponta (provado com o mesmo fixture local que os testes do `captcha_relay.py` já usavam) — abre navegador, preenche campo, detecta captcha clássico, pausa, aguarda humano, retoma, submete, captura resultado. O que falta é **uma pessoa com acesso de navegador real** (você, ou testando direto no Render) inspecionar por exemplo `processual.trf1.jus.br` uma vez e confirmar os `id`/`name` exatos dos campos — aí o mesmo mecanismo já testado aponta pra lá sem mudar nada de código.

## O que foi criado

- `app/bots/base.py` — `BotResult` e `BaseBot` (interface comum).
- `app/bots/datajud_bot.py`, `stj_bot.py`, `precatorio_bot.py`, `certidao_bot.py` — cada um é um wrapper fino em cima do que já existe em `diligencia_engine.py` (não duplica lógica — o hotfix anterior mostrou o preço real de duplicar a mesma regra em dois lugares).
- `app/bots/evidence_bot.py` — salva evidência vinculada, reaproveitando `ManualEvidence`.
- `app/bots/portal_bot.py` — reaproveita `captcha_relay.py` inteiro (não recria nada); explica o achado do robots.txt no próprio docstring.
- `app/bots/runner.py` — decide quais bots acionar pra cada dado, roda cada um (uma falha não derruba as demais), agrega num resultado humano único.
- `BotJob` e `BotStep` (modelos novos em `app/models.py`).
- `POST /api/bots/run`, `GET /api/bots/jobs`, `GET /api/bots/jobs/{id}`, `POST /api/bots/jobs/{id}/resume`, `GET /api/bots/status`.
- `status_em_portugues()` em Python (`certificate_center.py`) — a MESMA tradução que já existia só em JavaScript, agora também no backend, pra qualquer bot ou cliente de API (não só a tela) receber linguagem humana.
- Botão "🤖 Mandar bots trabalharem" na tela, com painel mostrando cada bot e seu status, incluindo a imagem de captcha + campo pra resolver quando o PortalBot pausa.
- `tests/test_bots.py` — 16 testes novos.

## O que foi alterado

- `app/main.py` — os 5 endpoints novos; `/api/diligencia` não mudou de comportamento.
- `app/schemas.py` — `BotsRunRequest`, `BotsResumeRequest`.
- `app/services/certificate_center.py` — `status_em_portugues()` adicionado; `steps` do plano ganhou o campo `status_humano`.
- `app/templates/index.html` — botão novo + painel de execução.

## Testes

`pytest -q` → **238 passed** com navegador / **230 passed, 8 skipped** sem navegador (6 de sempre do `captcha_relay` + 2 novos do PortalBot, mesma razão: exigem Chrome real).

Achado técnico ao escrever os testes: `TestClient` + Playwright no mesmo processo causa conflito real (erro `EPIPE` no processo Node do driver do Playwright) neste ambiente — os testes de PortalBot usam `asyncio.run()` chamando o bot direto, o mesmo padrão que os testes existentes de `captcha_relay.py` já usavam (não por acaso). A cobertura end-to-end via HTTP real (endpoint completo, incluindo `/resume`) foi confirmada manualmente com curl, com sucesso, e está descrita abaixo.

## Checklist manual (definição de pronto)

- [x] A) CNJ → DataJudBot aciona (testado com CNJ federal, DataJud mockado e real-mas-inalcançável-do-sandbox).
- [x] B) Sequencial STJ → StjBot aciona.
- [x] C) Sem XLSX → StjBot registra pendência de verdade (`"STJ aguardando upload do XLSX oficial."`), salva no job, não é só texto solto.
- [x] D) Certidão → CertidaoBot classifica em automática/configurável/manual, sempre em português.
- [x] E) Portal público real tentado — **mecanismo comprovado** com o fixture (mesmo código que rodaria contra um site real), mas sem alvo ao vivo configurado nesta entrega (ver seção acima).
- [x] F) Intervenção → job fica `waiting_user`, retomável via `/api/bots/jobs/{id}/resume` (testado ponta a ponta, incluindo captcha certo e errado).
- [x] G) Evidências salvas — `EvidenceBot.registrar_evidencia_automatica()` testado.
- [x] H) Job mostra o que cada bot fez (`GET /api/bots/jobs/{id}` com steps).
- [x] I) Histórico salva o trabalho — via `BotJob`/`BotStep`.
- [x] J) Testado em viewport de iPhone (390×844).

## O que ainda depende de você

- Confirmar os seletores de campo de um portal real (TRF1 é o candidato validado quanto a robots.txt) — depois disso, um `/api/bots/run` com `portal_url`/`portal_fill_fields`/`portal_submit_selector` já aciona de verdade.
- Provider comercial continua opcional, não implementado, como decidido.
