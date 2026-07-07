# v31 — WhatsApp Intake Manual

Escopo fechado como confirmado: modo manual só, sem OCR, sem API paga de visão, sem WhatsApp Business ativado, sem fonte nova, sem mexer em Judit, sem refazer arquitetura.

## Os dois exemplos obrigatórios, confirmados de ponta a ponta

**Exemplo 1** — `"O número 00007659720235070016. Fortaleza/CE."`
- CNJ normalizado: `0000765-97.2023.5.07.0016` ✅
- Segmento: Justiça do Trabalho ✅
- Tribunal provável: **TRT7** ✅ (confirmado contra fonte oficial do Portal CNJ: TRT7 = Ceará)
- Cidade/UF: Fortaleza/CE ✅
- Bots acionados, dossiê gerado, resposta sugerida mencionando TRT7/CE ✅

**Exemplo 2** — `"Número do processo 5000563.34.2022.4.03.6331. INSS. CPF xxx. Nome Júlio..."`
- CNJ normalizado (separador de ponto, não hífen): `5000563-34.2022.4.03.6331` ✅
- Segmento: Justiça Federal ✅
- Tribunal provável: **TRF3** ✅ (confirmado: TRF3 = SP/MS)
- INSS identificado como ente devedor ✅
- CPF extraído e mascarado (nunca em claro) ✅
- Nome extraído ✅
- **Divergência Pará/TRF1 vs. TRF3**: testado com "PA" e com "Pará" por extenso — os dois geram o alerta corretamente: *"Você mencionou PA, mas o número [...] indica TRF3 (Justiça Federal), que cobre MS, SP — não PA."* ✅

Testado nos dois pelo backend E pela tela (viewport de celular, 390×844).

## Checklist de fechamento (pedido específico desta rodada)

1. **Interação entre testes do webhook** — corrigida. Causa real: meu teste mexia direto num objeto `settings` que fica dessincronizado depois que outros testes (do PortalBot) chamam `get_settings.cache_clear()`. Troquei pro padrão robusto (variável de ambiente + cache_clear), imune à ordem de execução dos outros arquivos.
2. **Nenhum CPF/CNPJ completo na resposta visual** — confirmado; a API nunca devolve as chaves `cpf`/`cnpj` em claro, só as versões mascaradas.
3. **`texto_original` mascarado** — corrigido. Achado real: eu excluía as chaves `cpf`/`cnpj` da resposta, mas o texto original digitado (ecoado de volta) ainda trazia o número completo do jeito que a pessoa escreveu. Agora qualquer CPF/CNPJ dentro do texto livre é mascarado antes de devolver.
4. **CNJ não gera CPF/CNPJ falso** — corrigido. Achado real: o próprio CNJ de 20 dígitos continha, por coincidência, uma sequência de 11 dígitos que passava no regex solto de CPF. Agora os dígitos já identificados como CNJ são removidos antes de procurar CPF/CNPJ.
5. **Inferência correta, com fonte oficial**:
   - TRT7 = Ceará ✅ (Portal CNJ)
   - TRF3 = SP/MS ✅ (Portal CNJ)
   - Divergência Pará/TRF1 × TRF3 ✅ — testado com sigla ("PA") e nome por extenso ("Pará"), incluindo o caso difícil de não confundir "Mato Grosso" com "Mato Grosso do Sul".
6. **Intake aciona BotJob quando há CNJ** — confirmado, `job_id` retornado e testado.
7. **Print sem OCR salva evidência e pede texto manual** — confirmado, nunca trava o fluxo.
8. **Tela funciona no celular** — confirmado em viewport 390×844, fluxo completo (extrair → divergência → bots → dossiê → resposta sugerida).

## O que foi criado

- `app/services/whatsapp_intake.py` — extração/normalização/divergência/resposta sugerida.
- `app/bots/intake_bot.py` — aciona os bots existentes quando há processo detectado.
- `Lead`, `WhatsAppMessage`, `IntakeCase` (modelos novos).
- `POST /api/intake/whatsapp/manual`, `POST /api/intake/whatsapp/screenshot`.
- `GET/POST /api/whatsapp/webhook` — endpoints preparados, **não ativados** (webhook GET exige `WHATSAPP_VERIFY_TOKEN` configurado; sem isso, sempre 403. POST sempre devolve 501 nesta versão).
- Botão "Nova diligência do WhatsApp" na tela — texto colado ou print (sem OCR).
- `tests/test_whatsapp_intake.py` (22 testes).

## O que foi alterado

- `app/utils/cnj.py` — inferência de tribunal estendida pra Justiça do Trabalho (TRT1-24), necessário pro exemplo 1. Como consequência direta (e correta), 2 testes antigos que documentavam essa lacuna como "não coberto ainda" foram atualizados — não é regressão, é a lacuna sendo fechada.
- `app/config.py` — campo `whatsapp_verify_token` (vazio por padrão = webhook desativado).

## Testes

`pytest -q` → **295 passed** com navegador / **285 passed, 10 skipped** sem navegador. Confirmado do ZIP extraído do zero.

## O que falta pra ligar OCR e WhatsApp Business depois

- **OCR**: exige escolher um provider (API paga de visão, ou biblioteca local tipo Tesseract) — decisão que não tomei sozinho, como combinado. O endpoint de print já está pronto pra receber o resultado do OCR no lugar do "cole o texto manualmente" quando isso for decidido.
- **WhatsApp Business Cloud API**: exige você ter conta Meta Business configurada e gerar o `WHATSAPP_VERIFY_TOKEN` — os endpoints já existem e seguem o contrato da Meta (challenge/verify), só precisam desse token real pra sair do modo "preparado, não ativado".

## Como usar no dia a dia

1. Cliente manda mensagem no seu WhatsApp pessoal.
2. Copia o texto, cola em "Nova diligência do WhatsApp" no buscador.
3. Clica "Extrair e iniciar bots".
4. Vê na hora: processo normalizado, tribunal provável, divergência (se houver), o que ainda falta pedir, e uma resposta pronta pra colar de volta no WhatsApp (revisando antes de enviar).
5. Se só tiver print (sem conseguir copiar o texto), sobe o print — ele vira evidência, e o campo de texto continua ali embaixo pra colar manualmente.
