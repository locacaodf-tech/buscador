# v30.1 — Bots Maturados

Não mexi em fonte, arquitetura, registry, Judit ou motor novo — só a maturação pedida. Achei mais um bug real além da lista original, corrigido também.

## O erro principal, confirmado exatamente como reportado

Reproduzi antes de corrigir: `input=15547` sem XLSX carregado — o bot individual dizia "STJ aguardando upload do XLSX oficial" corretamente, mas o job ficava `completed`. Causa raiz: a agregação de status só checava `'falhou'` e `'waiting_user'`, nunca `'pendente'` — então uma pendência real não rebaixava o status do job. Corrigido com uma função separada e testável (`calcular_status_job`), com a regra exata pedida:

- `waiting_user` em qualquer bot → job `waiting_user` (prioridade máxima)
- todos os bots que rodaram falharam → `failed`
- qualquer `pendente` ou `falhou` → `partial`
- tudo `concluido` → `completed`

**Testes A e B da sua auditoria, confirmados**:
- A) `15547` sem XLSX → StjBot `pendente`, job `partial` ✅
- B) `PRC 123456` sem XLSX/tribunal/ano → StjBot `pendente`, PrecatorioBot `concluido` (gerou o plano mesmo com pendências dentro), job `partial` ✅

## O que mais foi corrigido

1. **`/api/diligencia` com `run_bots`** — `{"input": "...", "run_bots": true}` agora aciona os bots também, devolvendo `diligencia_id` + `job_id` + `bots_resumo`. Sem esse campo (ou `false`), comportamento idêntico a antes — testado que não quebrou nada.
2. **`GET /api/bots/jobs/{id}/dossie`** — página HTML com input, tipo, status geral (em português), cada bot com status/evidência/próxima ação.
3. **EvidenceBot de verdade integrado** — cada bot (DataJud/STJ/Precatório/Certidão) agora salva uma evidência automática, com `evidence_id` gravado no `BotStep`. Achei e corrigi um bug irmão nesse processo: o `evidence_id` já estava sendo salvo no banco, mas o endpoint `GET /api/bots/jobs/{id}` nunca devolvia esse campo na resposta — só apareceu escrevendo o teste.
4. **PortalBot sem alvo não conta como executado** — já era assim por design (confirmado com teste novo); `/api/bots/status` agora deixa isso explícito ("mecanismo pronto, requer alvo configurado").
5. **Frontend**: status geral do job traduzido (Concluído/Parcial/Aguardando ação sua/Falhou), não mais a palavra crua em inglês.

## Bug adicional encontrado escrevendo os testes (fora da lista original)

Rodando a suíte inteira (não só os arquivos novos isolados), a bateria travava de verdade — não era falha, era travamento (timeout). Isolei: minha própria função de limpeza de teste chamava `asyncio.run()` uma segunda vez logo depois do `TestClient`, o que conflita com o gerenciamento de loop de eventos do Playwright neste ambiente. Simplifiquei a limpeza (só remove a sessão do registro global, sem tentar fechar o navegador de forma assíncrona ali) — resolvido, confirmado sem travar, dos dois lados (com e sem navegador), e do ZIP extraído do zero duas vezes.

Também achei e corrigi um teste antigo da v30 que ficou desatualizado pela regra nova: com CNJ, só o DataJudBot roda — se ele falhar sozinho, isso é "tudo que rodou falhou" (`failed`), não `partial`. Ajustei esse teste e adicionei um novo cobrindo falha genuinamente parcial (dois bots, um falha e o outro conclui).

## Testes

`pytest -q` → **259 passed** com navegador / **249 passed, 10 skipped** sem navegador. Confirmado do ZIP extraído do zero.

Novo: `tests/test_bots_maturados.py` (20 testes) — cobre a regra de agregação isoladamente (6 testes), os 2 cenários exatos da sua auditoria, `run_bots`, dossiê do job, `evidence_id` por bot, PortalBot sem/com alvo, job `waiting_user` persistindo até resume.

## Checklist

- [x] STJ sem XLSX → BotJob `partial`.
- [x] Precatório sem XLSX/tribunal/ano → BotJob `partial`.
- [x] STJ com XLSX → BotJob `completed`.
- [x] `/api/diligencia` com `run_bots=true` devolve `job_id`.
- [x] `/api/diligencia` sem `run_bots` mantém comportamento antigo (testado).
- [x] `GET /api/bots/jobs/{id}/dossie` retorna HTML.
- [x] DataJudBot, StjBot, CertidaoBot salvam `evidence_id`.
- [x] PortalBot sem alvo não é contado como executado; com alvo, cria o step.
- [x] Job `waiting_user` permanece assim até o resume.

## O que ainda depende de você

Mesma coisa da v30: um alvo de portal com seletores confirmados por navegador real (TRF1 é o candidato liberado pelo robots.txt). Nada mudou nisso — não é escopo desta rodada.
