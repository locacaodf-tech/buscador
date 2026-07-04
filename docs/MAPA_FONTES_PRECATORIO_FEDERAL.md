# Mapa de Fontes Federais de Precatório — CJF e TRF1-TRF6

Consolida o que já foi pesquisado e verificado sobre as fontes federais de precatório/RPV/requisitório (CJF + 6 Tribunais Regionais Federais). Os dados aqui vêm do registry real (`app/services/official_precatorio_sources.py`) e do conector `app/connectors/cjf_trf_precatorios.py` — nada foi inventado pra este documento, é a consolidação do que já estava espalhado em comentários de código.

## CJF — Conselho da Justiça Federal

- **Status**: `mapped_public_dashboard` — painel público mapeado, ainda sem conector de busca implementado.
- **URL**: https://www.cjf.jus.br/publico/rpvs_precatorios/
- **Busca por**: CNJ, número de requisitório, número de precatório, RPV, ano-orçamento.

## TRF1 — 1ª Região (o mais avançado)

- **Status**: `implemented_partial` — **o único com busca real funcionando**, mas só por CNJ/número de processo.
- **URL**: https://processual.trf1.jus.br/consultaProcessual/
- **Busca declarada (mas não toda implementada)**: CPF, CNPJ, nome, OAB, CNJ, número de processo, requisitório, precatório, RPV.
- **Limitação real confirmada**: a busca por CPF/CNPJ/nome/OAB usa JavaScript/AJAX que a pesquisa não conseguiu confirmar nos parâmetros exatos — só o caminho por CNJ foi validado ao vivo.

## TRF2 — 2ª Região

- **Status**: `requires_credentials` — exige certificado digital/credencial desde 2024 (segredo de justiça ampliado). Não dá pra automatizar sem credencial institucional.
- **URL**: https://www10.trf2.jus.br/consultas/precatorio-e-rpv/

## TRF3 — 3ª Região

- **Status**: `public_form_to_implement` — formulário público identificado, conector ainda não escrito.
- **URL**: https://web.trf3.jus.br/consultas/internet/consultareqpag

## TRF4 — 4ª Região

- **Status**: `source_mapping_required` — só o domínio institucional confirmado, formulário específico ainda não mapeado em detalhe.
- **URL**: https://www.trf4.jus.br/

## TRF5 — 5ª Região

- **Status**: `public_form_to_implement` — formulário público identificado, com campos mais ricos que os outros (sequencial, processo de execução, processo originário, processo no TRF5, requisitório).
- **URL**: https://rpvprecatorio.trf5.jus.br/

## TRF6 — 6ª Região (Minas Gerais)

- **Status**: `router_to_implement` — a consulta depende da origem do processo (PJe do TRF1 ou eproc do TRF6), por isso é tratado como um "roteador" a implementar, não um formulário único.
- **URL**: https://portal.trf6.jus.br/rpv-e-precatorios/consulta-precatorio-e-rpv/

## Prioridade sugerida pra completar

1. TRF1: completar CPF/CNPJ/nome/OAB (já tem CNJ funcionando, é o mais próximo de terminar).
2. TRF5: formulário já mapeado, com campos ricos — bom custo-benefício.
3. TRF3: formulário já identificado.
4. CJF: painel público mapeado, falta conector.
5. TRF6: precisa resolver o roteamento PJe/eproc antes de implementar busca.
6. TRF4: precisa de pesquisa mais profunda antes de implementar.
7. TRF2: só avança com credencial institucional — fora do controle de pesquisa pública.
