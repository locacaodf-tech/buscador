
---

## Correções aplicadas pelo Claude sobre esta v23 (03/07/2026)

Boa ideia, execução com o mesmo problema da vez anterior: **2 dos 3 pontos de sintaxe quebrada continuavam sem correção** (só "Carregando capacidades" foi corrigido; "Carregando histórico" e "Solicitando no servidor" ainda quebravam a tela inteira). De novo, `pytest -q` não pega isso porque não toca o JavaScript.

Também: este pacote foi construído em cima da v22 antiga (sem minhas correções de isolamento de teste), não da v23 que eu já tinha corrigido e publicado.

**O que fiz**: apliquei a funcionalidade nova (orientador de preenchimento, normalização de CPF/CNPJ/OAB, campos UF/Tribunal/Ano-orçamento) por cima da minha versão já corrigida — não da deles. Testado com Playwright de verdade: seletor de tipo atualiza o orientador ao vivo, CPF com pontuação normaliza pra só números, OAB tipo "15547/DF" separa número e preenche UF sozinho, tudo sem erro de console. `pytest -q` → 134 passed.
