# v29 — Persistência e Dossiê da Diligência

Preservei tudo da v28 (motor, DataJud, STJ, certidões, evidências, diagnóstico). Não recomecei nada.

## O que foi criado

- **`DiligenciaLog`** (modelo novo em `app/models.py`) — salva cada chamada a `POST /api/diligencia` por completo: entrada original, tipo identificado, valor normalizado, resumo, próxima ação, resultados confirmados, indícios, pendências, fontes manuais, e o JSON avançado.
- **`GET /api/diligencias`** — lista as últimas diligências (mais recente primeiro).
- **`GET /api/diligencias/{id}`** — reabre uma diligência salva, com todo o detalhe.
- **`GET /api/diligencias/{id}/dossie`** — página HTML própria (`app/templates/dossie.html`), imprimível, mostrando dado pesquisado, resumo, resultados confirmados, indícios (com aviso de que não é confirmação oficial), pendências, fontes manuais, próxima ação e data/hora.

## O que foi alterado

- **`POST /api/diligencia`** agora salva o resultado no banco e devolve `diligencia_id` junto da resposta de sempre — nada mudou pra quem já usava o endpoint, só ganhou um campo a mais.
- **Tela**: depois de uma busca livre, aparece "✅ Diligência salva nº X" com botão "Abrir dossiê →". Uma área nova "Últimas diligências" no hub principal mostra as últimas 5, cada uma com link direto pro dossiê, atualizada automaticamente a cada nova busca.
- **Limpeza correta, sem tocar no que está vivo**: removi 3 funções de código morto do modo demonstração (`demoDossier`, `renderSimpleResult`, `demoCertTribunais`) que nunca são chamadas nesta versão (a tela é sempre conectada, same-origin). Uma delas, aliás, ainda tinha o link antigo/errado do TJSP que eu já tinha corrigido no registry real há semanas — ficou como prova de que dado "de demonstração" desatualizado é risco de confusão futura, não só estética. **Não toquei** nas traduções de status que também usam essas mesmas palavras-chave (`source_mapping_required` etc.) em outros lugares — essas são o tradutor de linguagem humana em uso ativo, não sobra de demo.

## Testes

`pytest -q` → **208 passed** com navegador / **202 passed, 6 skipped** sem navegador (mesmos 6 de sempre, do `captcha_relay`).

Novos: `tests/test_diligencia_persistencia.py` (11 testes) — cobre exatamente a lista pedida: cria log e devolve id, lista ordenada, reabre por id, 404 pra id inexistente, dossiê HTML com conteúdo real, 404 no dossiê inexistente, CPF sem provider salva a orientação, STJ com XLSX salva o resultado, CNJ mockado salva, pendências são salvas, próxima ação sempre salva.

## O que não fiz, de propósito (conforme pedido)

- Não validei DataJud ao vivo no Render (meu ambiente não alcança a rede real — só validável lá).
- Não mexi em `captcha_relay` (fora de escopo desta rodada, como pedido).
- Não criei fonte nova nem robô novo.

## Checklist manual

- [x] `POST /api/diligencia` cria `DiligenciaLog` e devolve `diligencia_id`.
- [x] `GET /api/diligencias` lista, mais recente primeiro.
- [x] `GET /api/diligencias/{id}` reabre com todo o detalhe.
- [x] `GET /api/diligencias/{id}/dossie` mostra HTML real, com aviso de indício ≠ confirmação oficial.
- [x] Tela mostra "Diligência salva nº X" + botão "Abrir dossiê".
- [x] "Últimas diligências" aparece no hub e atualiza sozinha.
- [x] JSON continua só no `<details>` recolhido.

## Como usar no dia a dia

1. Abra `https://buscador-processos.onrender.com`, digite qualquer dado na Busca livre.
2. Cada busca fica salva automaticamente — não precisa fazer nada a mais.
3. Pra reabrir depois: role até "Últimas diligências" no hub, ou acesse direto `/api/diligencias/{numero}/dossie` pelo número que apareceu.
4. O dossiê é uma página só, imprimível (Ctrl+P vira PDF direto no navegador, sem precisar de exportação especial).
