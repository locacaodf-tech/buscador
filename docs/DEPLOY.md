# Deploy — acesso web privado (iPhone e qualquer navegador)

Este guia cobre 3 formas de colocar o Buscador de Processos numa URL HTTPS acessível de fora, sem expor nenhum token. Escolha uma para começar; dá pra trocar depois sem perder nada (o projeto continua sendo o mesmo FastAPI + SQLite).

> **Dois arquivos de Render, escolha um só:**
> - `render.yaml` — plano **gratuito**, sem disco persistente. Uploads do STJ e evidências manuais podem se perder num reinício. Bom pra testar.
> - `render-production.yaml` — plano pago (~$7/mês), **com disco persistente** montado em `/data`. `STJ_UPLOAD_DIR` e `EVIDENCE_UPLOAD_DIR` apontam pra lá, então uploads e evidências sobrevivem a reinícios. Pra renomear esse pro ativo: `cp render-production.yaml render.yaml` antes do deploy.

**Antes de tudo, em qualquer uma das 3 opções:**

1. Preencha o `.env` local (nunca vai pro Git, nunca vai pro código):
   ```bash
   cp .env.example .env
   ```
2. Defina uma senha de acesso à tela:
   ```bash
   APP_LOGIN_PASSWORD=escolha-uma-senha-forte
   ```
   Sem isso, a tela fica aberta pra qualquer um que tiver a URL.
3. Defina um `APP_SECRET` forte (assina o cookie de sessão do login):
   ```bash
   APP_SECRET=uma-string-aleatoria-grande-e-diferente-do-default
   ```
4. Só depois preencha `DATAJUD_API_KEY` (já vem uma pública padrão) e, quando tiver, `JUDIT_API_KEY`.

---

## Opção A — Teste rápido com Cloudflare Tunnel ou ngrok

Serve pra você testar no iPhone hoje, sem contratar nada. A URL muda a cada reinício (a menos que configure um túnel fixo), então não é a solução final — é só o jeito mais rápido de validar.

### Cloudflare Tunnel

```bash
# 1. Rode o app normalmente na sua máquina
cd claude-buscador-processos
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 2. Em outro terminal, instale o cloudflared (uma vez só)
brew install cloudflared   # macOS

# 3. Abra o túnel apontando pro seu servidor local
cloudflared tunnel --url http://localhost:8000
```

O terminal mostra uma URL do tipo `https://algo-aleatorio.trycloudflare.com`. Abra essa URL no Safari do iPhone.

### ngrok (alternativa)

```bash
brew install ngrok
ngrok http 8000
```

Mesma lógica: ele te dá uma URL `https://....ngrok-free.app` pra usar no iPhone.

**Importante:** com túnel, sua máquina precisa estar ligada e com o `uvicorn` rodando. Assim que desligar, a URL para de funcionar. Bom pra teste, ruim pra uso do dia a dia.

---

## Opção B — Render ou Railway (recomendado para uso contínuo)

URL fixa, HTTPS automático, não depende da sua máquina ligada. Os arquivos `render.yaml` e `railway.json` já estão prontos na raiz do projeto.

### Render

1. Suba o projeto num repositório Git (GitHub/GitLab) — sem o `.env`, ele já está no `.gitignore`.
2. No painel do Render: **New > Blueprint**, aponte pro repositório. Ele lê o `render.yaml` sozinho.
3. Render vai pedir pra você preencher manualmente (não vêm no arquivo, por segurança):
   - `DATAJUD_API_KEY`
   - `JUDIT_API_KEY` (deixe vazio se ainda não tiver)
   - `INTERNAL_API_TOKEN`
   - `APP_LOGIN_PASSWORD`
4. `APP_SECRET` é gerado automaticamente pelo Render (`generateValue: true` no yaml).
5. O disco persistente de 1GB já está configurado, montado em `/data`, com `DATABASE_URL` apontando pra lá — o histórico de buscas sobrevive a redeploys.
6. Deploy. Render te dá uma URL `https://buscador-processos.onrender.com` (ou parecido).

### Railway

1. Mesmo repositório Git.
2. No painel do Railway: **New Project > Deploy from GitHub repo**. Ele detecta o `railway.json` e usa o Dockerfile.
3. Em **Variables**, adicione manualmente: `DATAJUD_API_KEY`, `JUDIT_API_KEY`, `INTERNAL_API_TOKEN`, `APP_LOGIN_PASSWORD`, `APP_SECRET`, `APP_ENV=production`.
4. Para persistir o SQLite entre deploys, adicione um **Volume** no Railway montado em `/app/data` e ajuste `DATABASE_URL=sqlite:////app/data/buscador_processos.db`. Sem isso, o banco reseta a cada deploy (aceitável pra validar, não pra produção real).
5. Railway gera a URL pública automaticamente (`https://seu-projeto.up.railway.app`).

---

## Opção C — VPS própria com Docker

Mais controle, mais trabalho de manutenção (você cuida de atualizações, backup, certificado).

```bash
# Na VPS (Ubuntu, por exemplo)
git clone <seu-repositorio>
cd claude-buscador-processos
cp .env.example .env
nano .env   # preencha as chaves e senhas

docker compose up -d --build
```

Isso sobe o app na porta 8000 da VPS, com o `docker-compose.yml` já configurado para:
- persistir o SQLite em `./data` (fora do container);
- reiniciar sozinho se cair (`restart: unless-stopped`);
- healthcheck automático em `/health`.

Falta só o HTTPS. Duas formas simples:

**Com Caddy (mais simples, certificado automático):**
```bash
# instale o Caddy na VPS, depois crie /etc/caddy/Caddyfile com:
seudominio.com.br {
    reverse_proxy localhost:8000
}
sudo systemctl reload caddy
```

**Com Nginx + Certbot (mais comum, mais configuração):**
- proxy reverso do Nginx pra `localhost:8000`;
- `certbot --nginx` pra gerar o certificado Let's Encrypt.

Aponte o DNS do seu domínio pra o IP da VPS antes de rodar qualquer um dos dois.

---

## Como acessar pelo iPhone

Depois de ter uma URL HTTPS pronta (de qualquer uma das 3 opções):

1. Abra o Safari (ou Chrome) no iPhone.
2. Digite a URL (`https://...`).
3. Você cai na tela de **login** — digite a senha que você colocou em `APP_LOGIN_PASSWORD`.
4. Depois de logado, o painel funciona normal: campo de busca, seletor de provedor, tribunais etc.
5. Opcional: no Safari, toque em **Compartilhar > Adicionar à Tela de Início** — fica com ícone de app, sem barra de navegador.

A sessão fica salva por 90 dias por padrão (configurável via `SESSION_TTL_DAYS` no `.env`). Pra sair, toque em **Sair** no topo da tela.

---

## Como não expor a JUDIT_API_KEY

- Ela mora **só** no `.env` local ou nas variáveis de ambiente da plataforma de deploy (Render/Railway têm campos próprios pra isso, marcados como secretos no `render.yaml`/dashboard).
- Nunca aparece no código, no `git log`, nem em nenhum arquivo versionado — o `.gitignore` já bloqueia `.env`.
- O navegador do iPhone **nunca** vê essa chave. Ela é usada só no backend, quando o servidor chama a API da Judit. O que trafega até o navegador é só o resultado da busca já processado.
- Se em algum momento ela vazar (print, log, commit por engano), revogue no painel da Judit e gere outra.

## Como testar a rota /health

Essa rota não exige login nem token — é o endpoint que as plataformas de deploy (Render, Railway) usam pra saber se o app está de pé.

```bash
curl https://sua-url-publica.com/health
```

Deve responder `{"status":"ok"}`. Se isso falhar, o app não subiu — comece a depurar por aqui antes de qualquer outra coisa.

## Como abrir o painel após login

1. Acesse a URL raiz (`https://sua-url-publica.com/`).
2. Se `APP_LOGIN_PASSWORD` estiver configurada, você é redirecionado pra `/login` automaticamente.
3. Digite a senha, clique em **Entrar**.
4. Você volta pra `/` já autenticado — o campo "Token interno" da tela pode ficar vazio, a sessão de login já autoriza as buscas.
5. Pra sair de qualquer página, vá direto em `/logout` ou clique em **Sair** no topo do painel.

---

## O que NÃO mudou nesta entrega

Conectores (DataJud, Judit, tribunal_precatorios), orchestrator, normalizer, classifier de precatório e o banco SQLite continuam exatamente como estavam na v5. Só foram adicionados: login simples por sessão, arquivos de deploy, e este guia.

## Próxima etapa (fora do escopo desta entrega)

Login avançado com cadastro de usuários, múltiplos perfis de acesso e cobrança/plano mensal ficam para depois, quando fizer sentido para o negócio.
