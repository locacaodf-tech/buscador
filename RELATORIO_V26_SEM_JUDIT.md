# v26 — Sem Judit, dados reais do STJ, busca livre e correções da auditoria

Direção explícita sua: não conectar Judit, ser melhor que ela dentro do que já temos de graça. Tudo abaixo respeita isso — nenhuma menção a Judit sobrou empurrando configuração em lugar nenhum da tela.

## O que resolve "ser melhor que a Judit" sem pagar ninguém

**Busca por nome dentro dos dados do STJ que você já carrega.** O parser já reconhecia a coluna de credor/beneficiário (`credor_nome`) desde antes, mas nunca era usada na busca — só existia no bastidor. Agora: digita um nome na "Busca livre", ela procura nos arquivos XLSX que você já subiu, sem acento, sem case sensitive, parcial (ex.: "maria da silva" acha "MARIA DA SILVA SOUZA"). Sem arquivo carregado, orienta a subir primeiro — nunca inventa resultado.

**Busca livre de diligência** — campo único no topo da tela: digite CPF, CNPJ, nome, OAB, CNJ, precatório, RPV, requisitório ou sequencial, e ela identifica sozinha e leva pro fluxo certo:
- CNJ → análise de processo (DataJud)
- Nome → busca nos dados do STJ
- Sequencial → tela do STJ
- CPF/CNPJ/OAB → diz com honestidade que não há fonte gratuita pra isso isolado, sem empurrar nenhum provedor específico, e sugere tentar por nome ou CNJ

## Correções da auditoria externa — verificadas uma a uma antes de aplicar

1. **CNJ consultava os 6 TRFs à toa.** Confirmado no código: sem tribunal explícito, ia em `FEDERAL_TRIBUNALS` inteiro. O próprio número CNJ já diz qual TRF é (dígitos posição 14-15 = segmento+tribunal). Agora infere e consulta só 1, com fallback pros 6 quando não dá pra inferir (ex.: CNJ estadual).
2. **Dockerfile não instalava o navegador do Playwright** — confirmado (só instalava a biblioteca Python via pip). `captcha_relay` não funcionaria em produção. Adicionado `playwright install --with-deps chromium` no build. *Não consigo testar o build Docker completo aqui (sem Docker no meu ambiente) — vale você confirmar no primeiro deploy.*
3. **Evidências manuais não tinham pasta configurável** — confirmado, era um caminho fixo. Adicionado `EVIDENCE_UPLOAD_DIR`, mesmo padrão do `STJ_UPLOAD_DIR`, já nos dois `render.yaml`.
4. **Docs desatualizados** — confirmado ("14 dias" quando já é 90). Corrigido, e adicionada nota clara no topo do `DEPLOY.md` sobre os dois arquivos de Render e as pastas de persistência.
5. **"Falta busca livre"** — endereçado acima, mas redesenhado sem Judit, focado no que já existe de graça.

## Novo: "Ver se minha ferramenta está pronta"

Painel de diagnóstico (link no rodapé do hub): mostra em português se DataJud/STJ/Serpro/login estão ativos, sem expor nenhuma chave, com status neutro (não empurra Judit).

## Testes

`pytest -q` → **180 passed**, 0 failed, 0 warnings. Novos: `test_datajud_connector.py` (8, inclui a inferência de tribunal), `test_diagnostico.py` (5), busca por nome em `test_stj_precatorios.py` (+5).

## Arquivos alterados

- `app/utils/cnj.py` — `infer_federal_tribunal()` novo.
- `app/connectors/datajud.py` — usa a inferência antes de consultar todos os TRFs.
- `app/connectors/stj_precatorios.py` — `match_records` aceita `search_type='name'`.
- `app/schemas.py` — `StjSearchRequest` aceita `'name'`.
- `app/config.py` — `evidence_upload_dir` novo.
- `app/services/manual_evidence.py` — pasta configurável (mesmo padrão do STJ).
- `app/main.py` — endpoint `/api/diagnostico` novo; mensagem da Judit no diagnóstico sem empurrar configuração.
- `app/templates/index.html` — busca livre, painel de diagnóstico, correção de bug real (classe `.voltar-hub` duplicada causava navegação ambígua), mensagens sem Judit.
- `Dockerfile` — instala Chromium do Playwright.
- `render.yaml`, `render-production.yaml` — `EVIDENCE_UPLOAD_DIR` adicionado.
- `docs/DEPLOY.md` — correção de 14→90 dias, nota sobre os dois render.yaml.
- Testes novos/atualizados conforme acima.

## O que ainda não fiz, de propósito

- Não implementei fonte nova nem mexi em captcha/scraping.
- Build Docker completo não testado aqui (sem Docker no ambiente) — só a lógica em Python.
- Busca por nome funciona só nos dados do STJ que você carregar — não existe (ainda) outra fonte gratuita de precatório com nome de beneficiário mapeada; se quiser expandir pra outras fontes depois, dá pra crescer esse mesmo mecanismo.
