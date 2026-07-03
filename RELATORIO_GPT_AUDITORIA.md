# Auditoria GPT — v22 operacional

Auditoria feita sobre `claude-buscador-processos-v21-tudo-junto.zip`.

## Resultado dos testes

Após instalar `requirements.txt`:

```bash
pytest -q
# 134 passed
```

## Correções feitas

1. **Sessão persistente para uso no iPhone/navegador**
   - Adicionada variável `SESSION_TTL_DAYS`.
   - Default: 90 dias.
   - O token assinado e o cookie agora usam o mesmo TTL configurável.
   - Objetivo: logar uma vez e não precisar digitar senha toda hora.

2. **Uploads STJ configuráveis/persistentes**
   - Adicionada variável `STJ_UPLOAD_DIR`.
   - Local/teste: `data/stj_uploads`.
   - Produção Render com disco: `/data/stj_uploads`.
   - O serviço `stj_uploads.py` agora respeita a variável, preservando compatibilidade com testes.

3. **Render separado por finalidade**
   - `render-free.yaml`: plano free, sem disco persistente; útil para teste rápido.
   - `render-production.yaml`: plano starter com disco persistente em `/data`; adequado para uso real.

4. **Tela limpa de mensagens antigas**
   - Removidas mensagens visíveis antigas sobre URL de backend, CORS, token interno e modo demonstração.
   - A tela agora assume same-origin: o backend serve o HTML e as chamadas são relativas ao próprio servidor.

5. **Captcha relay mais robusto em teste**
   - Em ambientes que bloqueiam `file://` no Chromium, fixtures locais são carregadas por `page.set_content()`.
   - Isso não altera a lógica de produção para URLs reais; só evita falso erro no teste.

## Arquivos alterados

- `app/config.py`
- `app/main.py`
- `app/services/stj_uploads.py`
- `app/services/captcha_relay.py`
- `app/templates/index.html`
- `.env.example`
- `render.yaml`
- `render-production.yaml`
- `render-free.yaml` (novo)
- `RELATORIO_GPT_AUDITORIA.md` (este arquivo)

## Recomendação de uso

Para validação rápida:

- usar `render-free.yaml`;
- aceitar que uploads/histórico podem sumir em reinício.

Para operação real:

- usar `render-production.yaml`;
- configurar `APP_LOGIN_PASSWORD`;
- manter `SESSION_TTL_DAYS=90`;
- manter `STJ_UPLOAD_DIR=/data/stj_uploads`;
- usar disco persistente.

## Próxima fase recomendada

Não adicionar novas fontes ainda. Primeiro validar o ciclo operacional:

1. abrir o site;
2. fazer login;
3. carregar XLSX do STJ;
4. consultar sequencial;
5. montar dossiê;
6. consultar fontes;
7. consultar certidões mapeadas.

Depois disso, implementar fontes reais por prioridade comercial.

---

## Correções aplicadas pelo Claude sobre esta v22 (03/07/2026)

As ideias abaixo eram boas e foram mantidas. Mas a execução tinha 2 problemas reais, encontrados testando de verdade (não só rodando `pytest -q`):

### 1. Bug crítico: JavaScript quebrado (derrubava a tela inteira)

3 linhas em `app/templates/index.html` ficaram com sintaxe inválida depois da limpeza de mensagens antigas (ex.: `setLoading('Carregando capacidades do servidor'…');` — aspa fechando antes das reticências, sem concatenação). Isso quebra o `<script>` inteiro — nenhum botão funcionaria.

**Por que `pytest -q` não pegou isso**: os testes em Python não carregam nem executam o JavaScript da tela. Só um `node --check` no JS extraído, ou abrir a página de verdade num navegador, pega esse tipo de erro. Corrigido e confirmado com `node --check` + Playwright rodando a tela de verdade (login, 4 botões, sessão) sem nenhum erro no console.

### 2. Bug real: STJ_UPLOAD_DIR quebrava o isolamento dos testes

Com `STJ_UPLOAD_DIR` configurado no `.env` (exatamente como a própria v22 recomenda), 4 testes de `test_stj_uploads.py` passavam a escrever todos na mesma pasta real em vez de pastas isoladas por teste — um teste contaminava o outro. A fixture de teste só isolava a constante antiga `UPLOAD_DIR`, mas o novo `upload_dir()` prioriza o settings quando ele está preenchido. Corrigido isolando também `upload_dir()` na fixture.

**Resultado após as duas correções**: `pytest -q` → 134 passed (confirmado com `STJ_UPLOAD_DIR` configurado, não só sem ele). Testado com Playwright real: sessão de 90 dias confirmada no cookie, upload do STJ indo pra pasta configurada (simulando disco persistente do Render), zero erros de JavaScript no console.
