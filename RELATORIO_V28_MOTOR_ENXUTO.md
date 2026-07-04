# v28 — Motor Operacional de Diligência (enxuto)

Preservei tudo: DataJud, STJ XLSX, upload de evidências, diagnóstico, histórico, certidões mapeadas, source registry, testes, login, Render/Docker, normalizadores de CPF/CNPJ/CNJ/OAB, tela atual. Nada foi apagado nem recomeçado.

Criei `app/services/diligencia_engine.py`.
Criei `POST /api/diligencia`.
A tela agora chama esse endpoint em vez de decidir tudo em JavaScript.
CPF/CNPJ/OAB sem provider mostra orientação clara — nunca finge que pesquisou.
Nome busca de verdade nos dados do STJ carregados.
CNJ consulta DataJud pelo backend, com falha limpa quando indisponível.
Sequencial STJ busca no XLSX, orienta upload quando falta.
Precatório/RPV gera plano operacional.
Certidão gera plano por fonte (objetivo=certidao).
JSON fica só num `<details>` recolhido, nunca aberto por padrão.
Testes: **197 passed** com navegador disponível / **191 passed, 6 skipped** sem navegador (os 6 são do `captcha_relay`, que exige navegador de verdade).

## O que foi reaproveitado (não duplicado)

- `infer_identifier()` (já existia em `identifier.py`) — a mesma detecção de tipo que antes eu tinha duplicado em JavaScript.
- `DataJudConnector` — chamado direto, sem reimplementar a lógica de tribunal.
- `stj_uploads.search_uploaded_files()` — mesma busca por sequencial/nome/processo já testada antes.
- `build_precatorio_route_plan()` — mesmo planejador de precatório/RPV.
- `build_certificate_plan()` — mesmo planejador de certidões.

## O que foi criado

- `app/services/diligencia_engine.py` — o motor em si.
- `app/services/providers/base.py` — interface preparada pra provider comercial futuro (Protocol, não implementado — Judit continua funcionando via `/api/search` como já funcionava, isso aqui é só a forma pro futuro).
- `app/schemas.py` — `DiligenciaRequest` adicionado.
- `tests/test_diligencia_engine.py` — 14 testes novos, cobrindo a lista pedida (CPF/CNPJ sem provider, nome com/sem STJ, CNJ mockado, DataJud falhando, sequencial com/sem XLSX, precatório, certidão, próxima ação sempre presente, endpoint ponta a ponta).

## O que foi alterado

- `app/main.py` — endpoint `/api/diligencia` adicionado, sem tocar nos endpoints existentes.
- `app/templates/index.html` — `handleBuscaLivre()` agora chama o backend em vez de decidir tudo no JavaScript. Também corrigi um bug real que encontrei nesse processo: a caixa de "registro manual de evidência" reusa os mesmos IDs em dois lugares (CNJ e busca livre) — sem limpar o conteúdo do painel anterior ao trocar de tela, isso criava IDs duplicados no DOM. Corrigido limpando as duas áreas ao trocar de painel.

## O que funciona sem nenhum provider comercial

CNJ (DataJud), STJ por sequencial/processo/nome (arquivo que você carrega), plano de precatório/RPV, plano de certidões, evidência manual, diagnóstico.

## O que só vai funcionar com um provider comercial configurado (Judit ou outro)

Busca nacional por CPF/CNPJ/OAB isolados — sem mais nenhum dado, sem provider, o motor explica isso claramente e sugere tentar por CNJ, nome (no STJ) ou registrar manualmente. A interface (`providers/base.py`) já está pronta pra receber isso no futuro, sem precisar redesenhar o motor.

## Checklist manual

- [x] Digitei CPF → orientação clara, sem resultado falso.
- [x] Digitei nome → busca no STJ XLSX quando há arquivo carregado.
- [x] Digitei CNJ → consulta DataJud pelo backend.
- [x] Digitei sequencial STJ → busca no XLSX.
- [x] Digitei precatório/RPV → plano operacional.
- [x] Pedi certidões (objetivo=certidao) → plano por fonte.
- [x] Registrei evidência manual — reaproveitado do fluxo já existente.
- [x] Testado em viewport de iPhone (390×844) em todos os passos acima.
