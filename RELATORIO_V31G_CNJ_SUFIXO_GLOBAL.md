# v31g — CNJ com Sufixo Global + Prioridade Documental

Escopo fechado: só essa inconsistência. Nada de fonte nova, OCR, WhatsApp Business ou arquitetura nova.

## Os dois bugs confirmados e a causa raiz de cada um

### 1. `infer_identifier` nunca recebeu o fix de sufixo

O fix da v31e/f só tocou `whatsapp_intake.py`. A função central `infer_identifier()` — usada por `/api/diligencia`, `/api/bots/run`, `/api/search` e a tela "Analisar processo por CNJ" — tinha sua PRÓPRIA lógica de contagem de dígitos (`only_digits(key)` cru), nunca passava pelo `normalize_cnj` corrigido. Por isso `0016114-59.2017.8.26.0053/01` virava `tipo_identificado: unknown` em todo lugar, menos no IntakeBot.

**Corrigido** trocando pra `normalize_cnj`/`split_cnj_suffix` na função central. Confirmado nos 4 pontos, com teste automatizado pra cada um:
- `/api/diligencia` → `tipo_identificado: cnj` ✅
- `/api/search` → `search_type: cnj` ✅
- `/api/bots/run` (DataJudBot) → aciona corretamente, consulta com CNJ base ✅
- Tela "Analisar processo por CNJ" → **achei um TERCEIRO lugar com o mesmo bug**: a validação client-side em JavaScript tinha sua própria contagem de dígitos, independente do Python. Corrigida também — era exatamente o fluxo que você estava usando no celular.

### 2. Mensagem rica perdia pra "peça CPF/nome" quando DataJud consultava com sucesso e vinha vazio

Causa: minha checagem só olhava `job.status in {partial, failed}`. Mas "DataJud consultado com sucesso, retornou vazio" deixa o step (e o job) como `concluido` — nunca `partial`. Corrigido pra checar o `status_consulta` real do step (`consultado_sem_resultado`/`falhou`), não só o status agregado do job.

**Achei um terceiro caso durante o teste**: quando o DataJud falha com uma exceção genérica (não `ConnectorError`), o step fica `falhou` mas sem `status_consulta` preenchido — minha primeira correção não cobria esse caso. Ajustei pra também tratar `step.status == 'falhou'` diretamente.

## Confirmado nos dois casos exatos, com DataJud mockado pra retornar vazio (não erro)

**Ofício requisitório TJSP**: *"Consultamos o DataJud para o TJSP usando o CNJ base 0016114-59.2017.8.26.0053 (o sufixo /01 do documento indica incidente/desdobramento...), mas não houve retorno. Como o documento é um ofício requisitório/precatório, a fonte principal de confirmação deve ser o TJSP/DEPRE."*

**Ação rescisória TJBA**: *"CNJ válido e tribunal inferido: TJBA. A consulta DataJud não retornou resultado para este número. Como o documento indica ação rescisória e traz processo referência, consulte também o processo referência 8000694-09.2025.8.05.0043."*

Nenhum dos dois cai mais em "Peça também: CPF ou CNPJ, Nome completo".

## Testes

`pytest -q` → **374 passed** com navegador / **364 passed, 10 skipped** sem navegador. Confirmado do ZIP extraído do zero.

Novo: `tests/test_cnj_sufixo_global.py` (13 testes) — cobre os 10 itens pedidos, incluindo o caso de falha de rede genérica que eu mesmo achei testando.

## Arquivos alterados

- `app/services/identifier.py` — a correção central.
- `app/main.py` — checagem de "sem resultado" agora olha o status real da consulta.
- `app/templates/index.html` — validação client-side da tela CNJ corrigida (terceiro lugar com o bug).
