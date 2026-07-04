# v27 — correções da auditoria externa (v26)

## Correção da minha própria imprecisão, sem rodeio

No relatório da v26 eu escrevi "180 passed, 0 failed, 0 warnings" sem repetir a ressalva que eu mesmo já tinha usado antes (que 6 desses testes, do `captcha_relay`, só passam se houver Chrome/Chromium disponível no ambiente que roda o teste). A auditoria rodou sem navegador e viu 174 passed, 6 skipped — matematicamente é o mesmo total (174+6=180), mas eu deveria ter sido preciso de novo, e não fui. Não vou repetir isso:

**Número exato, testado dos dois jeitos agora:**
- Com navegador disponível: **183 passed**.
- Sem navegador: **177 passed, 6 skipped** (os 6 do `captcha_relay`, que exige navegador de verdade pra testar — isso é esperado, não é falha).

## Sobre "nenhuma menção a Judit sobrou"

Minha frase foi imprecisa por não deixar o escopo claro. O que é verdade: as telas novas (busca livre, diagnóstico, CNJ) não empurram mais configurar Judit. O que também é verdade, e a auditoria pegou certo: o conector Judit continua existindo no código (nunca pedi pra apagar ele, só parar de empurrar), e a mensagem de erro do DataJud pra busca de nome/CPF citava Judit por nome — ajustei essa mensagem também, pra ficar consistente (agora não cita nenhum provedor específico, e aponta pra busca por nome do STJ como alternativa real que já existe).

## Correções aplicadas, verificadas uma a uma

1. **`total_sources` faltava em `/api/sources`** — confirmado, adicionado (66+34+11=111), com teste.
2. **Produção sem senha fica aberta** — confirmado como risco real. Em vez de só logar isso (que ninguém vê), criei um **alerta vermelho visível na própria tela**, toda vez que `APP_ENV=production` e `APP_LOGIN_PASSWORD` estiver vazio. Testado de verdade no navegador.
3. **Mensagem do DataJud citando Judit por nome** — suavizada, sem nomear provedor específico, apontando pra busca por nome do STJ (que resolve parte real do caso).

## O que não fiz, de propósito

- **`/api/diligencia-livre` como endpoint de backend separado**: é uma sugestão de arquitetura razoável (deixaria a lógica de identificar tipo reutilizável fora do HTML), mas não fiz agora — você já tinha pedido antes pra eu não mexer em arquitetura profunda enquanto o foco for utilidade. A lógica atual (no JavaScript da tela) já funciona e foi testada ponta a ponta; migrar isso pra um endpoint é trabalho de estrutura, não de utilidade nova. Se quiser essa migração numa próxima rodada, é só pedir.
- **Limpeza de menções a CORS/token nos docs técnicos**: a própria auditoria reconhece que isso não aparece na tela principal — são documentos técnicos (deploy, arquitetura, captcha) descrevendo mecanismo real do sistema, não erro visível. Deixei como está.
- **DataJud ao vivo**: continua não testável do meu ambiente (rede restrita). Só é validável no Render mesmo.

## Testes

`pytest -q` → 183 passed com navegador / 177 passed + 6 skipped sem navegador. Confirmado do ZIP extraído do zero, dos dois jeitos.

## Arquivos alterados

- `app/services/source_master.py` — `total_sources`.
- `app/main.py` — flag `alerta_producao_sem_senha`.
- `app/templates/index.html` — banner vermelho de alerta.
- `app/connectors/datajud.py` — mensagem sem citar Judit por nome.
- `tests/test_source_master.py`, `tests/test_main_routes.py` — testes novos.
