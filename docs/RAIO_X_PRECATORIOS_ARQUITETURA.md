# Raio-X Processual e Camada Oficial de Precatórios/LOA

Esta versão acrescenta uma camada separada para não confundir **indício processual via DataJud** com **confirmação oficial de precatório/RPV/orçamento**.

## Correção importante feita nesta rodada

A v8 recebida tinha uma regressão real: o conector `cjf_trf_precatorios` (TRF1, consulta por CNJ/processo, testado ao vivo em turno anterior) tinha sido removido — `official_precatorio_sources.py` só descrevia a fonte de forma declarativa, sem nenhuma chamada HTTP de verdade. **Foi restaurado.** Ele volta a ser a única fonte oficial com consulta real funcionando: `provider=cjf_trf_precatorios`, tribunal TRF1, tipo `cnj`/`numero_processo`.

Também corrigido: o registro do TRF2 dizia `source_mapping_required` sem mencionar que, desde a Resolução TRF2-RSP-2024/00082, precatórios/RPVs do TRF2 correm em segredo de justiça e exigem certificado digital de advogado. Agora está `requires_credentials=True`.

## Endpoints

- `GET /api/official-precatorio/sources` — lista as 66 fontes mapeadas, com `summary` (contagem por status e por escopo) e `status_meanings` (o que cada status quer dizer).
- `POST /api/official-precatorio/plan` — devolve o plano de busca por camadas (processo → requisitório → LOA/orçamento → fila/pagamento), sem inventar dado de nenhuma fonte não implementada.
- `POST /api/dossier` — combina a busca processual real (DataJud/Judit/cjf_trf_precatorios) com o plano oficial.
- `POST /api/official-precatorio/browser-search` — **novo nesta rodada.** Aciona um conector de automação de navegador por `source_id`. Hoje todos são stubs (ver seção Portal Automation abaixo) — a resposta é sempre honesta (`status: not_implemented`), nunca 500 e nunca dado inventado.

## Cobertura do registry (66 fontes)

- Nacional: SisPreq/PDPJ, MPO/SIOP, LOA Câmara/União.
- Justiça Federal: CJF + TRF1-TRF6 (pesquisados e verificados; ver `docs/MAPA_FONTES_PRECATORIO_FEDERAL.md`).
- Justiça estadual: os 27 (25 TJs adicionados nesta rodada + TJDFT e TJSP que já existiam).
- Justiça do Trabalho: os 24 TRTs + CSJT.
- Tribunais superiores: STF, STJ, TST, STM.

**Importante sobre honestidade dos dados**: só CJF e TRF1-TRF6 foram de fato pesquisados (buscas web reais, verificadas ao vivo). Os outros 52 (TJs, TRTs, CSJT, STF/STJ/TST/STM) entraram no registry com status `not_researched` — só o domínio institucional (convenção `.jus.br`, informação pública estável) está preenchido; nenhum campo de capacidade (aceita CPF? tem captcha? retorna LOA?) foi respondido, porque eu não pesquisei essas 52 fontes individualmente nesta rodada. Preencher isso agora seria inventar dado, que é exatamente a regra que você pediu para nunca quebrar.

## Portal Automation (arquitetura, não scrapers funcionando)

Criado `app/services/portal_automation.py` com:
- `PortalAutomationConnector` — classe base abstrata com os métodos pedidos (`can_search`, `build_query`, `run_browser_search`, `extract_results`, `normalize_results`, `detect_blockers`);
- `AutomationStatus` — constantes `requires_manual_action`, `requires_login`, `requires_certificate`, `captcha_detected`, entre outras;
- 8 stubs (`trf1_precatorios_browser` ... `tjsp_precatorios_browser`) que declaram a fonte mas levantam `NotImplementedError` em qualquer método real.

**Por que não entreguei um scraper "funcionando"**: o ambiente onde este código foi escrito não tem acesso de rede aos domínios dos tribunais — só uma ferramenta de pesquisa que devolve HTML convertido em markdown, sem DOM real, sem conseguir rodar Playwright de verdade. Publicar um conector Playwright com seletores que eu nunca vi funcionar seria inventar que funciona. `Playwright` não foi adicionado ao `requirements.txt` — é uma dependência pesada (~300MB com Chromium) que não faz sentido pesar no deploy antes de existir código real usando ela.

## Regra de produto (mantida)

A tela/relatório deve sempre separar:

1. `Indício processual` — DataJud/Judit/movimentações/classes.
2. `Registro oficial de precatório/RPV` — tribunal/CJF/SAPRE/SisPreq.
3. `LOA/orçamento` — Câmara/SIOP/CJF/relatórios por exercício.
4. `Fila/pagamento` — tribunal/portal de precatórios.
5. `Cálculo e oportunidade` — só depois de obter valor/data/status.

## Sobre remover o campo de token da tela

Você pediu para tirar o campo de token/chave da tela. Não fiz isso ainda, de propósito, porque a resposta certa depende de qual tela:

- **Painel embutido no FastAPI** (`app/templates/index.html`): já resolvido há duas entregas. Se você fizer login com `APP_LOGIN_PASSWORD`, o cookie de sessão já autoriza as buscas sozinho — o campo de token pode ficar vazio. Ele só aparece porque também serve pra quem quer acessar via script/curl sem passar pela tela.
- **Artifact HTML standalone** (o que você testou pelo iPhone, hospedado fora do domínio do backend): esse é cross-origin. Cookie de sessão não atravessa domínios sem eu mudar o modelo de CORS para aceitar credenciais (`allow_credentials=True` + `SameSite=None`), o que é uma mudança de segurança relevante o suficiente para eu não fazer sem confirmar com você. Sem token OU cookie cross-origin, não existe forma segura de autorizar aquele HTML a chamar o backend.

Proposta: quando você tiver o backend publicado de verdade, decidimos juntos se vale a pena habilitar cookie cross-origin (aí sim o token some da tela) ou se o token fica só como campo avançado escondido por padrão. Não quis tomar essa decisão sozinho porque ela afeta segurança, não só UX.

## Plano de implementação por prioridade

1. **MPO/SIOP dados abertos** — orçamento federal/LOA em CSV público, sem captcha/login. Melhor custo-benefício técnico.
2. **TRF1 — completar CPF/CNPJ/nome/OAB** — mesma fonte que já funciona para CNJ, só falta confirmar os parâmetros exatos dos formulários.
3. **TJDFT/SAPRE** — essencial para DF, mas primeiro precisa confirmar se dá para automatizar sem sessão/captcha (indício encontrado: aplicação com sessão, "sessão expirada" numa tentativa simples de acesso).
4. **TRF5** — portal público bem estruturado, mapear campos.
5. **TRF3** — requisições de pagamento, CPF/CNPJ + 1 campo.
6. **CJF** — só painel informativo, baixa prioridade como conector.
7. **SisPreq/PDPJ** — só quando houver credencial institucional.
8. **Demais TJs/TRTs/STF/STJ/TST** — pesquisar por prioridade comercial, um de cada vez, do mesmo jeito rigoroso que fiz com CJF/TRF1-6 (buscas reais, verificação ao vivo, nunca preencher capacidade sem confirmar).

## Exemplo de teste

```bash
curl -s -X POST http://127.0.0.1:8000/api/official-precatorio/plan \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: defina_um_token" \
  -d '{"search_type":"cnj","search_key":"0032681-47.2017.4.01.3400","extra_params":{"tribunal":"TRF1","ano_orcamento":"2026"}}'

curl -s -X POST http://127.0.0.1:8000/api/official-precatorio/browser-search \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: defina_um_token" \
  -d '{"source_id":"tjdft_sapre_browser","search_type":"cpf","search_key":"12345678900"}'
```

