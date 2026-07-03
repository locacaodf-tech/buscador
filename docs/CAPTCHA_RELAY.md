# Captcha Relay — automação com pausa para você resolver o captcha

## O que é

Um mecanismo genérico (`app/services/captcha_relay.py`) que abre um navegador real (Playwright), navega até uma URL, preenche os campos que você indicar e:

- **Se achar um captcha clássico** (imagem com texto distorcido + campo pra digitar): **para**, tira print da imagem e devolve pra você. Você resolve. Manda o texto de volta. A automação digita e submete. Ela nunca resolve sozinha.
- **Se não achar captcha nenhum**: segue e submete direto, devolve o resultado.
- **Se achar reCAPTCHA/hCaptcha**: para e avisa que este mecanismo não serve pra esse tipo — reCAPTCHA é um desafio comportamental ("marque que não é robô", análise de mouse/tempo), não um "digite o texto que vê". Não dá pra resolver preenchendo um campo.

## Prova de que funciona de verdade

Diferente de outras partes do projeto onde só consegui pesquisar (sem executar), aqui consegui **testar o mecanismo completo, de ponta a ponta, com navegador real rodando**: criei uma página de teste com um captcha de verdade (imagem gerada, código "K9R2X"), e o teste automatizado prova que o sistema:
1. Abre a página, preenche o campo de documento;
2. Detecta a imagem do captcha e o campo de código;
3. Tira print real da imagem (não um placeholder);
4. Pausa e devolve uma sessão;
5. Recebe o código resolvido, digita, submete;
6. Confirma sucesso com o código certo e rejeição com o código errado.

Achei e corrigi 2 bugs reais rodando esse teste (não só escrevendo código): a variável de configuração do Chrome não estava sendo lida corretamente, e a checagem de "captcha rejeitado" dava falso positivo porque batia no código-fonte do `<script>` da página, não no texto realmente exibido — corrigido removendo script/style antes de checar.

Também testei que reCAPTCHA é detectado e recusado educadamente, sem tentar resolver.

## O que ainda não está resolvido: nenhum alvo real confirmado

Este mecanismo funciona — provado com meu próprio alvo de teste. Mas **não tenho, até agora, nenhuma fonte oficial de precatório/certidão com captcha clássico confirmado** para apontar ele. O único captcha que confirmei em pesquisas anteriores (antecedentes criminais da PF) é reCAPTCHA — exatamente o tipo que este mecanismo não resolve.

Próximo passo real: você (ou eu, numa sessão com acesso à rede desses sites) precisa encontrar um formulário real com captcha de imagem clássico — muitos sistemas mais antigos de tribunal ainda usam esse padrão — e aí eu aponto os seletores certos (URL, campos, botão) pra este mecanismo.

## Como usar

```bash
# 1) Inicia a sessão
curl -X POST http://SEU_BACKEND/api/portal-automation/start \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: seu_token" \
  -d '{
    "source_id": "algum_tribunal",
    "url": "https://site-do-tribunal.jus.br/consulta",
    "fill_fields": {"#cpf": "12345678900"},
    "submit_selector": "#btnConsultar"
  }'
# -> {"status":"captcha_required","session_id":"...","captcha_image_base64":"..."}
# decodifique captcha_image_base64 e olhe a imagem

# 2) Resolve
curl -X POST http://SEU_BACKEND/api/portal-automation/SESSION_ID/solve \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: seu_token" \
  -d '{"captcha_text": "o que você leu na imagem"}'
# -> {"status":"success","html":"..."} ou {"status":"captcha_rejected", ...}
```

Sessão expira em 5 minutos se ninguém resolver (evita navegador pendurado consumindo memória).

## Implicações reais de deploy — leia antes de publicar

Playwright + Chromium **pesam de verdade**: ~300-400MB adicionais na imagem de deploy. Isso muda a conta:

- **Render/Railway free tier**: pode não ter RAM/disco suficiente. Provavelmente precisa de um plano pago.
- **Precisa rodar `playwright install --with-deps chromium`** depois do `pip install`, ou apontar `PLAYWRIGHT_CHROME_PATH` pra um Chrome já instalado no host.
- **Servidor com estado**: diferente do resto da API (sem estado, cada requisição é independente), aqui a sessão de navegador fica aberta na memória do processo entre o `start` e o `solve`. Isso não funciona bem com múltiplas instâncias/auto-scaling atrás de um load balancer sem sticky sessions — para o seu volume atual, um único servidor (VPS ou plano com 1 instância) resolve.
- **Nunca testei contra um site real** — só contra minha própria página de teste. A validação contra um alvo de verdade só acontece no seu ambiente.

## Regra que continua valendo

Isso não muda nada da regra de honestidade do projeto: nunca inventa dado, nunca resolve captcha sozinho, sempre mostra fonte/URL/data da consulta. É só mais um caminho técnico pra chegar no mesmo padrão de confiabilidade.
