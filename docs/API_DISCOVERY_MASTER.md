# API Discovery Master — mapa completo de fontes/APIs

Consolida tudo que existe no projeto em três camadas: **precatório oficial** (`official_precatorio_sources.py`, 66 fontes), **certidões** (`certificate_center.py`, 8 fontes) e **APIs processuais/institucionais/comerciais** (`source_master.py`, 11 fontes). Endpoint único: `GET /api/sources`.

**Regra de honestidade que rege este documento**: cada fonte tem um `integration_status`. Só existem duas categorias "prontas": `implemented` (roda de verdade, sem configuração extra — DataJud, Judit já configurada) e `implemented_configurable`/`implemented_partial` (o código existe e funciona assim que você fornecer uma credencial/contrato, ou funciona parcialmente). Todo o resto é honestamente "não pronto ainda", com o motivo específico.

---

## 1. APIs oficiais públicas

| Fonte | Status | Observação |
|---|---|---|
| DataJud/CNJ | **implemented** | Metadados processuais de todo o Brasil. Não resolve CPF/nome nem precatório/LOA oficial. |
| MPO/SIOP dados abertos | **implemented_partial** | CSV por exercício, nomes de coluna copiados da Nota Metodológica oficial do SOF/MPO. Sem CNJ/credor (proibido por lei). |
| Serpro Consulta CND | **implemented_configurable** | API REST real e documentada publicamente. Paga (Loja Serpro). Funciona assim que `SERPRO_CND_CONSUMER_KEY`/`SECRET` forem preenchidos. |
| Antecedentes Criminais (SINIC/PF) | **captcha_detected** | Portal público existe e é gratuito, mas usa reCAPTCHA — automação descartada pela regra do projeto. Existe API formal no Conecta gov.br, mas exige convênio institucional. |

## 2. APIs oficiais institucionais (exigem credencial/convênio)

| Fonte | Status | Observação |
|---|---|---|
| SisPreq/PDPJ-Br | requires_institutional_credentials | Sistema nacional de gestão de precatórios/RPVs. Swagger existe, mas em ambiente de gateway institucional. |
| SIOP WS Precatórios | requires_institutional_credentials | Confirmado: é o canal pelo qual os TRIBUNAIS enviam dados de precatórios à SOF (inclusão/alteração/cancelamento). Não serve para consulta por terceiros. |
| Comunica/PJe (DJEN) | requires_institutional_credentials | **Corrigindo uma imprecisão do texto que você recebeu**: a API é para tribunais enviarem publicações, com usuário/senha do Corporativo CNJ liberado por Administrador Regional — não é uma API pública de busca. Existe site público de busca (comunica.pje.jus.br), mas não confirmei API de leitura por trás dele. |
| MNI (PJe) | requires_institutional_credentials | Confirmado: webservice SOAP institucional, acesso por sistema credenciado. |
| Codex/CNJ | **not_researched** | Não verificado nesta rodada. Entrou no escopo por menção externa — não presumir capacidades. |
| BNMP | **not_researched** | Não verificado. Fora do foco principal (precatórios/certidão cível). |

## 3. Fontes oficiais por arquivo/portal (precatórios) — resumo

66 fontes completas em `official_precatorio_sources.py` / `GET /api/sources` → `precatorio_oficial`. Só o que já é real:

| Fonte | Status |
|---|---|
| TRF1 (CNJ/processo) | **implemented_partial** — testado ao vivo |
| STJ (XLSX oficial) | **implemented_partial** — upload manual, buscas reais funcionando |
| MPO/SIOP | **implemented_partial** — CSV oficial, colunas verificadas |
| TRF2 | requires_credentials — segredo de justiça desde 2024 |
| CJF, LOA Câmara, TJSP | mapeados, portal/dashboard sem API de busca própria |
| TRF3, TRF4, TRF5, TRF6, TJDFT | mapeados, formulário público identificado, conector ainda não implementado |
| 25 TJs + 24 TRTs + CSJT + STF/STJ/TST/STM | não pesquisados individualmente ainda |

## 4. Certidões (certificate_center)

| Fonte | Status | Observação |
|---|---|---|
| Serpro Consulta CND | **implemented_configurable** | Mesma API do item 1. |
| Regularize (PGFN) | source_mapping_required | Portal público gratuito, presença de captcha não verificada. |
| CJF Certidão Unificada | source_mapping_required | Confirmado: emite cível/criminal/eleitoral de **todos os TRFs de uma vez**. Fluxo do formulário não mapeado ainda. |
| TJs (base genérica) | not_researched | Cada TJ tem portal próprio; nenhum pesquisado individualmente. |
| STF, STJ certidões | not_researched | — |
| TST (inclui CNDT) | not_researched | Boa candidata a próxima pesquisa — muito usada em due diligence. |
| TRTs (base genérica) | not_researched | — |

## 5. APIs privadas/comerciais

| Fonte | Status | Observação |
|---|---|---|
| Judit | **implemented** | Já no projeto desde o início. Liga com `JUDIT_ENABLED=true` + `JUDIT_API_KEY`. |
| Escavador | not_researched | Alternativa comercial à Judit. Capacidades não verificadas nesta rodada — não presumidas. |
| Jusbrasil Soluções | not_researched | Idem. |
| Infosimples | not_researched | Provedor de automação de portais/certidões via API própria — apareceu nesta pesquisa como fonte terceira (documentou parâmetros do TRF1 e da validação de antecedentes criminais). Caminho prático para terceirizar automação de portais difíceis em vez de construir scraper próprio, se fizer sentido comercialmente. |

---

## Resumos automáticos (via `GET /api/sources` → campo `summary`)

- `prontos_para_uso_agora`: fontes com `implemented`/`implemented_partial`/`implemented_configurable`.
- `dependem_de_credencial_ou_contrato`: fontes institucionais ou pagas ainda não habilitadas.
- `exigem_automacao_de_navegador_ou_tem_captcha`: fontes onde captcha foi confirmado (hoje: antecedentes criminais PF).

## O que mudou de verdade nesta rodada

1. `app/services/certificate_center.py` (novo) — registry de 8 fontes de certidão + conector real e configurável do Serpro CND + endpoints `/api/certificates/sources`, `/plan`, `/request`, `/{id}`.
2. `app/services/source_master.py` (novo) — registry de 11 APIs processuais/institucionais/comerciais + agregador único.
3. `GET /api/sources` (novo) — visão única dos 3 registries (85 fontes ao todo).
4. `app/models.py` — `CertificateRecord` (histórico de pedidos de certidão).
5. **Duas correções factuais importantes** em relação ao texto que você recebeu de outra IA: Comunica/PJe não é API pública de busca (é institucional, para tribunais enviarem publicações), e Antecedentes Criminais da PF tem captcha confirmado (não dá pra automatizar).

## O que não foi feito, de propósito

- Não construí scrapers reais para TJs/TRTs individuais, CJF Certidão Unificada, TST/CNDT — nenhum foi pesquisado com o rigor que dei a TRF1/STJ/MPO-SIOP/Serpro nesta rodada. Fazer isso agora seria repetir o erro de inventar que funciona.
- Não contratei nem testei Escavador/Jusbrasil/Infosimples — são pagos, decisão comercial seria seu, e integrá-los sem verificar a API real seria a mesma armadilha.
- Não construí automação para Antecedentes Criminais PF — captcha confirmado, regra do projeto proíbe contornar.

## Próxima pesquisa recomendada (por prioridade)

1. **CJF Certidão Unificada** — maior alavancagem (cível/criminal/eleitoral de todos os TRFs de uma vez), fluxo ainda não mapeado.
2. **TST/CNDT** — muito usada em due diligence, não pesquisada.
3. **TJDFT certidões** — dado seu foco em DF.
4. Completar TRF3/TRF4/TRF5 no `official_precatorio_sources` (formulário já identificado, falta implementar).
