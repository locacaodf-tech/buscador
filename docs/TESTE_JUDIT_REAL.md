# Teste Judit com API Key real

Roteiro objetivo para quando você tiver a chave. Não mexe em código, só em `.env` e nas chamadas de teste.

---

## 1. Preencher o `.env`

No arquivo `.env` (nunca no código, nunca commitado):

```bash
JUDIT_ENABLED=true
JUDIT_API_KEY=sua_chave_real_aqui
JUDIT_REQUESTS_BASE_URL=https://requests.production.judit.io
JUDIT_TRACKING_BASE_URL=https://tracking.production.judit.io
JUDIT_LAWSUITS_BASE_URL=https://lawsuits.production.judit.io
JUDIT_NAME_SEARCH_TYPE=name

INTERNAL_API_TOKEN=defina_um_token_seu
```

Se `INTERNAL_API_TOKEN` estiver preenchido, toda chamada abaixo precisa do header `X-Internal-Token`. Os exemplos já incluem esse header — se você deixar `INTERNAL_API_TOKEN` vazio, pode tirá-lo do curl.

## 2. Iniciar o servidor

```bash
cd claude-buscador-processos
source .venv/bin/activate   # ou crie com: python -m venv .venv && pip install -r requirements.txt
uvicorn app.main:app --reload
```

Confirme que subiu:

```bash
curl -s http://127.0.0.1:8000/health
```

Deve responder `{"status":"ok"}`.

## 3. Testar busca por CPF

```bash
curl -s -X POST http://127.0.0.1:8000/api/search \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: defina_um_token_seu" \
  -d '{"provider":"judit","search_type":"cpf","search_key":"12345678900"}'
```

Troque `12345678900` por um CPF real (só dígitos ou formatado, o sistema normaliza).

## 4. Testar busca por CNPJ

```bash
curl -s -X POST http://127.0.0.1:8000/api/search \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: defina_um_token_seu" \
  -d '{"provider":"judit","search_type":"cnpj","search_key":"00000000000191"}'
```

## 5. Testar busca por OAB

```bash
curl -s -X POST http://127.0.0.1:8000/api/search \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: defina_um_token_seu" \
  -d '{"provider":"judit","search_type":"oab","search_key":"123456","extra_params":{"uf":"SP"}}'
```

OAB costuma precisar da UF separada. Se a Judit devolver erro pedindo outro formato, ajuste o `extra_params` conforme a mensagem de erro retornada.

## 6. Testar busca por CNJ

```bash
curl -s -X POST http://127.0.0.1:8000/api/search \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: defina_um_token_seu" \
  -d '{"provider":"judit","search_type":"cnj","search_key":"0032681-47.2017.4.01.3400"}'
```

Esse é o processo do caso SINDJUS/DF que você já tem em andamento — bom teste de referência cruzada com o que sai no DataJud.

## 7. Testar busca por nome (com `JUDIT_NAME_SEARCH_TYPE=name`)

Confirme no `.env` que está `JUDIT_NAME_SEARCH_TYPE=name` (é o default) e reinicie o servidor se tiver acabado de mudar.

```bash
curl -s -X POST http://127.0.0.1:8000/api/search \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: defina_um_token_seu" \
  -d '{"provider":"judit","search_type":"name","search_key":"Nome Completo da Parte"}'
```

## 8. Se a busca por nome falhar, trocar para `nome`

Se o passo 7 vier com erro de tipo inválido (não confundir com "sem resultado", ver seção 9):

1. No `.env`, mude:
   ```bash
   JUDIT_NAME_SEARCH_TYPE=nome
   ```
2. **Reinicie o uvicorn.** Variável de ambiente é lida na inicialização — trocar o `.env` sem reiniciar não tem efeito.
3. Repita exatamente o mesmo curl do passo 7.

Nenhum código muda entre uma tentativa e outra, só o `.env` e o restart.

## 9. Como diferenciar os tipos de erro

A resposta sempre volta com HTTP 200 e o problema aparece dentro de `"warnings"` (isso já foi corrigido para não derrubar a request com 500). Olhe o texto do warning:

| O que aparece em `warnings` | O que significa | O que fazer |
|---|---|---|
| `Judit não está habilitada. Configure JUDIT_ENABLED=true e JUDIT_API_KEY.` | `.env` não está configurado ou não foi lido (esqueceu de reiniciar) | Confirme `.env` e reinicie o servidor |
| `Judit HTTP 401: ...` ou `Judit HTTP 403: ...` | **Erro de token** — chave inválida, expirada ou sem permissão para esse tipo de busca | Confira a `JUDIT_API_KEY`; se estiver certa, é caso para o suporte comercial da Judit |
| `Judit HTTP 422` ou `400` mencionando `search_type` | **Erro de tipo inválido** — provavelmente é o caso de "name" vs "nome" (ver passo 8), ou campo obrigatório faltando (ex.: UF da OAB) | Ajuste `JUDIT_NAME_SEARCH_TYPE` ou os `extra_params` conforme a mensagem |
| Menção a `Timeout`, `ConnectError`, `TransportError` ou similar | **Erro de rede** — Judit fora do ar, DNS, firewall/proxy da sua rede bloqueando o domínio | Teste a conectividade de fora da aplicação (`curl` direto pro domínio da Judit) antes de suspeitar do código |
| Nenhum warning, `"total": 0`, `"results": []` | **Ausência de resultado** — a chamada funcionou, só não achou nada pra esse identificador | Não é bug; teste com outro CPF/CNPJ/nome conhecido para confirmar que o conector está saudável |

## 10. Sobre a `JUDIT_API_KEY`

- Fica **somente** no `.env` local, que já está no `.gitignore`.
- Nunca cole a chave real em código, commit, print de tela ou nesta conversa comigo. Eu não preciso da chave para nada — todo o código já está pronto para lê-la do `.env`.
- Se a chave vazar por engano em algum lugar, revogue e gere uma nova no painel da Judit antes de continuar os testes.
