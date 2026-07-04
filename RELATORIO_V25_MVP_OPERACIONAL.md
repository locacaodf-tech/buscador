# v25 — MVP Operacional de Diligência

Entrega direta, sem arquitetura nova, sem fonte nova, sem registry novo. Reorganiza o que já existia num fluxo de 4 botões, mais registro manual de evidência.

## Checklist dos 4 fluxos — testados de verdade, não só descritos

- [x] **Fluxo CNJ funciona.** Testado com Playwright: digita CNJ → chama DataJud → mostra CNJ, tribunal, classe, assunto, órgão julgador, última movimentação, indícios, fonte, data. Se há indício de precatório, mostra bloco "Próxima etapa para confirmar precatório oficial" com a frase exata pedida, fonte provável, dados necessários, botão "Copiar dados para consulta" e link "Abrir fonte oficial →" (TRF1-6/CJF mapeados). Sem indício ou sem resultado, diz isso claramente com próxima ação.
- [x] **Fluxo STJ funciona.** Reaproveitado (já existia, testado antes e retestado agora após as mudanças no hub): sem XLSX, avisa "Arquivo oficial do STJ ainda não carregado" antes de deixar buscar. Com XLSX carregado, busca por sequencial e devolve sequencial, classe, processo, valor, previsão, arquivo, aba, linha, data do upload — sem mock, dado real da planilha.
- [x] **Fluxo precatório orientado funciona.** Novo: campos guiados (tribunal, tipo, CNJ, número, sequencial, ano-orçamento, CPF/CNPJ, nome) → gera plano categorizado (disponível agora / exige credencial / exige manual / não automatizado), diz exatamente quais dados faltam, e dá a próxima ação.
- [x] **Fluxo certidões orientado funciona.** Novo: escolhe pessoa física/jurídica, UF, tipo (cível/criminal/Receita-PGFN/trabalhista) → recomenda a fonte certa automaticamente (ex.: DF+cível → TJDFT; fiscal → Serpro/CND), com status em português, dados exigidos, link oficial e próxima ação. Nunca diz "nada consta" sem certidão real — só mostra status de integração.
- [x] **Tela usa linguagem humana.** Tradutor central (`STATUS_EM_PORTUGUES`) converte todo jargão técnico (`source_mapping_required`, `implemented_partial`, `requires_credentials` etc.) em frases operacionais.
- [x] **Sem JSON na cara.** Testado explicitamente: nenhuma tela do fluxo principal mostra `{"..."}` cru.
- [x] **Sem token, sem CORS, sem URL de backend.** A tela é servida pelo próprio backend (mesma origem) desde a v19 — isso já estava resolvido e continua.
- [x] **Sem fonte nova.** Nenhum conector, registry ou tribunal novo foi adicionado nesta rodada.
- [x] **Funciona no iPhone.** Testado em viewport 390×844 (tamanho de iPhone) em todos os fluxos.

## O que foi adicionado de verdade nesta rodada

**Registro manual de evidência** (item 9 do pedido): botão "📎 Registrar resultado manual" dentro do resultado do fluxo CNJ — cola texto encontrado manualmente e/ou anexa PDF/XLSX/print, salva vinculado à referência (CNJ/precatório). Backend novo, mas mínimo: 1 tabela (`ManualEvidence`), 1 serviço (`manual_evidence.py`), 2 endpoints (`POST`/`GET /api/evidencias`). Testado com 6 casos automatizados (texto, arquivo, extensão inválida rejeitada, registro vazio rejeitado, filtro por referência, nome de arquivo malicioso sanitizado).

## Arquivos alterados nesta rodada

- `app/templates/index.html` — hub reconstruído (4 botões exatos), fluxo CNJ novo, fluxo Precatório/RPV guiado novo, fluxo Certidões guiado novo, tradutor de status, registro manual de evidência na tela.
- `app/models.py` — tabela `ManualEvidence` adicionada; `datetime.utcnow()` trocado por `datetime.now(timezone.utc)` (aviso de depreciação corrigido).
- `app/services/manual_evidence.py` — novo, serviço de salvamento de evidência.
- `app/services/source_master.py` — expõe se a chave do DataJud em uso é a pública padrão ou uma configurada pelo usuário (sem nunca expor o valor).
- `app/config.py` — chave pública do DataJud como fallback centralizado (`resolved_datajud_api_key`), nunca hardcoded solta; `mask_api_key` pra nunca vazar valor completo.
- `app/connectors/datajud.py` — usa a resolução centralizada; nunca mais recusa inicializar por falta de chave.
- `app/main.py` — 2 endpoints novos de evidência; login com `hmac.compare_digest` (não `!=`) e rate limit (5 tentativas/15 min); migrado de `@app.on_event` pra `lifespan`; `TemplateResponse` na assinatura nova (request primeiro).
- `tests/test_manual_evidence.py`, `tests/test_datajud_key_resolution.py`, `tests/test_orchestrator.py`, `tests/test_main_routes.py` — novos.
- `tests/test_certificate_center.py`, `tests/test_source_master.py` — sincronizados com o código real (estavam desatualizados, causando falha).
- Correções menores herdadas da auditoria anterior: imports mortos removidos, nome de arquivo corrompido corrigido, link quebrado do TJSP corrigido, `render-free.yaml` redundante removido, `docs/MAPA_FONTES_PRECATORIO_FEDERAL.md` criado.

## Testes

`pytest -q` → **162 passed**, 0 failed, 0 warnings (rodando com um navegador disponível; sem navegador, 6 testes de `captcha_relay` pulam honestamente, o resto continua passando).

## Como usar (2 minutos, como pedido)

1. Acesse `https://buscador-processos.onrender.com` (ou rode local: `uvicorn app.main:app --reload`).
2. A tela abre direto nos 4 botões grandes.
3. Toque no que precisa fazer — cada botão leva direto pro campo certo, sem passar por tela nenhuma de configuração.

## O que ficou de fora, de propósito (conforme pedido: nada de fonte nova ou arquitetura profunda)

- Nenhum tribunal novo automatizado.
- Nenhuma automação de captcha nova testada contra site real.
- `docs/DEPLOY.md` e `README.md` ainda não atualizados com os detalhes desta rodada (próxima rodada, se fizer sentido).
