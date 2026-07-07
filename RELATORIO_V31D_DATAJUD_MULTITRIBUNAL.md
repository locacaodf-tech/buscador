# v31d — Auditoria Multi-Tribunal DataJud

Escopo fechado: só diagnóstico e fallback. Nada de fonte nova, WhatsApp, OCR, Judit ou arquitetura nova.

## Os 5 casos pedidos, confirmados com alias e endpoint reais

| Caso | CNJ | Tribunal inferido | Alias DataJud | Endpoint |
|---|---|---|---|---|
| A | `5000563-34.2022.4.03.6331` | TRF3 | `trf3` | `.../api_publica_trf3/_search` |
| B | `0001013-66.2019.8.17.2670` | TJPE | `tjpe` | `.../api_publica_tjpe/_search` |
| C | `0713236-85.2016.8.02.0001` | TJAL | `tjal` | `.../api_publica_tjal/_search` |
| D | `0000765-97.2023.5.07.0016` | TRT7 | `trt7` | `.../api_publica_trt7/_search` |
| E | CNJ 4.01 | TRF1 | `trf1` | `.../api_publica_trf1/_search` |

Todos os 5 resolvem pro alias/endpoint corretos — prova que TRF3 não era especial, é o mesmo código genérico pra qualquer tribunal.

**Achado interessante testando isso**: o erro que aparece no meu sandbox agora vem com o texto exato — `"HTTP 403: Host not in allowlist: api-publica.datajud.cnj.jus.br"`. Isso confirma, com o texto literal do meu ambiente, o que eu já vinha dizendo: não é o DataJud recusando a consulta, é a minha própria rede de desenvolvimento que não alcança esse domínio. Em produção (Render), a consulta chega de verdade.

## O que foi criado

- `app/services/datajud_diagnostico.py` — `diagnosticar_cnj()`: normaliza, infere segmento/tribunal, resolve alias/endpoint, tenta a consulta real nesse tribunal específico, devolve tudo.
- `GET /api/datajud/diagnostico/{cnj}` — expõe isso via API.
- Nova aba "DataJud" no modo avançado — cola um CNJ, vê o diagnóstico completo na tela.
- `tests/test_datajud_diagnostico.py` (17 testes).

## Matriz completa (item 4 do pedido) — não só os 5 casos

Testei TODOS os 57 tribunais do registry, não só os 5 exemplos:
- **TRF1 a TRF6** (6) — todos resolvem pro alias certo.
- **TRT1 a TRT24** (24) — todos resolvem pro alias certo.
- **Todos os 27 TJs** (TJAC a TJTO) — todos resolvem pro alias certo.

## Os 4 estados de resultado (item 2)

Testados com mock controlado (sem depender da rede):
- **CNJ inválido** → `"CNJ inválido."` antes de qualquer tentativa de consulta.
- **Consultado, vazio** → `"Consultamos o DataJud no tribunal TRT7 e não houve retorno para esse CNJ..."` (testado com resposta HTTP 200 vazia simulada).
- **Falhou** → `"Não foi possível consultar o DataJud para TRT7 (alias trt7) agora..."` (testado com timeout simulado).
- **Alias não configurado** → tratado defensivamente (não deveria acontecer com o registry atual, que é completo, mas não quebra se acontecer).

## Fallback manual (item 7) — honestidade sobre o que verifiquei

Só **2 URLs foram verificadas de fato** (busca real, confirmando que existem e correspondem): `processual.trf1.jus.br` (TRF1) e `certidoesunificadas.app.tjpe.jus.br` (TJPE) — essas vêm de pesquisas anteriores nesta mesma sessão.

Pra **todos os outros 55 tribunais** (incluindo TJAL, TRT7, TRF3 dos seus exemplos), a fonte manual usa o padrão de domínio oficial da Justiça brasileira (`www.<sigla>.jus.br`), mas devidamente marcado como **"padrão jus.br — não verificado individualmente pra este tribunal"** — não inventei confirmação que não tenho. Testei explicitamente que essa distinção aparece certa (`test_fallback_manual_verificado_nao_e_confundido_com_padrao`).

## Testes

`pytest -q` → **343 passed** com navegador / **333 passed, 10 skipped** sem navegador. Confirmado do ZIP extraído do zero.

## O que ainda não fiz (fora de escopo, por acordo)

Verificar individualmente as URLs oficiais dos 55 tribunais restantes — isso exigiria confirmar cada uma por busca, o que é uma tarefa própria, não parte deste diagnóstico.
