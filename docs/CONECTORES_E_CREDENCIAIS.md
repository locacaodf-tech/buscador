# Conectores e credenciais

Guia objetivo do que é preciso obter, por provedor, para ativar busca real por CPF, nome, CNPJ, OAB, número CNJ, número de processo, número de requisitório, número de precatório e número de RPV.

Nenhuma credencial real está incluída aqui nem no código. Este documento é só orientação para você decidir com quem contratar/credenciar antes de eu implementar cada conector.

---

## DataJud/CNJ

- **Busca aceita:** número CNJ e número de processo quando estiver no padrão CNJ (20 dígitos). Não busca por CPF, CNPJ, nome, OAB, nem tem campo universal de requisitório/precatório/RPV — só o que estiver indexado como classe/assunto/movimento do processo.
- **Credencial:** API Key pública, publicada na wiki do DataJud. Não exige convênio nem certificado. Pode mudar/rotacionar sem aviso.
- **Natureza:** oficial (CNJ).
- **Dificuldade:** baixa. Já implementado e testado neste projeto.
- **Prioridade:** já cumprida. Nenhuma ação necessária agora.

## Judit

- **Busca aceita:** CPF, CNPJ, OAB, nome, número CNJ, número de processo. Cobre mais de 90 tribunais (estadual, federal, trabalhista, eleitoral, militar, superior) e BNMP.
- **Credencial:** API key exclusivamente via header `api-key` (nunca `Authorization: Bearer`), conforme especificação confirmada por você. Solicitar chave com o comercial/conta Judit.
- **Natureza:** privada/comercial. Cadastro self-service, sem convênio institucional.
- **Dificuldade:** baixa. O conector já está implementado neste projeto (`app/connectors/judit.py`); falta só gerar o token e ativar `JUDIT_ENABLED=true` no `.env`.
- **Prioridade:** alta. É o caminho mais rápido para CPF/CNPJ/nome/OAB reais. Recomendo contratar primeiro.

## Escavador

- **Busca aceita:** CPF, CNPJ, OAB, nome, número CNJ (API Business v1/v2).
- **Credencial:** Personal Access Token (Bearer), gerado no painel da conta. Para acessar autos em segredo de justiça, aceita certificado digital A1 (e-CPF) de advogado cadastrado no tribunal — funcionalidade separada, não é obrigatória para busca básica.
- **Natureza:** privada/comercial. Cadastro self-service, cobrança por requisição (limite de 500 req/min).
- **Dificuldade:** baixa/média. Bem documentado, tem SDK Python oficial.
- **Prioridade:** média. Bom complemento/redundância à Judit, principalmente se precisar de autos em segredo de justiça via certificado digital. Não é urgente se a Judit já cobrir o volume.

## Jusbrasil

- **Busca aceita:** monitoramento e busca por nome, CPF/CNPJ (principalmente monitoramento de distribuição e movimentação; a API é menos voltada a consulta pontual do que Judit/Escavador).
- **Credencial:** API própria existe (api.jusbrasil.com.br/docs), mas o onboarding é menos self-service — historicamente depende de contato comercial para liberar acesso e definir escopo/preço.
- **Natureza:** privada/comercial.
- **Dificuldade:** média/alta, por causa do onboarding menos direto e da sobreposição de função com Judit/Escavador.
- **Prioridade:** baixa. Só avaliar se Judit/Escavador deixarem alguma lacuna específica de cobertura.

## SisPreq/PDPJ

- **Busca aceita, em tese:** precatório, RPV, requisitório, e dados do beneficiário (CPF/CNPJ) — é literalmente o sistema nacional de gestão de precatórios/RPVs do CNJ, lançado em setembro de 2025.
- **Credencial:** modelo institucional. A arquitetura é pensada para tribunais se integrarem via webhook/notificação (não é uma API pública de consulta aberta para terceiros). Existe portal web para consulta por credor/advogado (sispreq.pdpj.jus.br). Para acesso programático, o padrão usado em outros serviços da PDPJ (ex.: Domicílio Judicial Eletrônico) exige CNPJ + certificado digital + geração de credenciais pelo próprio portal PDPJ, com login via SSO (Keycloak).
- **Natureza:** oficial, mas com credencial institucional (não é um simples token de API comercial).
- **Dificuldade:** alta. Sistema muito recente (ainda com módulos pendentes por causa da EC 136/2025), sem API pública documentada para consumo por terceiros no momento.
- **Prioridade:** média/alta a médio prazo — é a fonte correta para requisitório/precatório/RPV — mas não é ganho rápido agora. Recomendo acompanhar a evolução e, se fizer sentido, consultar o portal manualmente enquanto isso, em vez de forçar um conector automatizado sem API oficial aberta.

## CJF

- **Busca aceita:** nenhuma diretamente. O CJF mantém uma página informativa (cjf.jus.br/publico/rpvs_precatorios) que apenas linka para os portais de cada TRF.
- **Credencial:** não aplicável como conector — o CJF não expõe API própria de consulta processual/precatório.
- **Natureza:** oficial, mas função regulatória/orçamentária, não uma API de busca.
- **Dificuldade:** não se aplica como conector isolado.
- **Prioridade:** baixa como conector. Tratar como referência normativa (resoluções, EC 136/2025), não como fonte de dados.

## TRF1 a TRF6

- **Busca aceita:** cada TRF tem seu próprio portal web de consulta de precatórios/RPV, tipicamente por CPF/CNPJ do beneficiário + número do processo/requisitório. Exemplos confirmados: TRF1 usa o sistema Sirea; TRF3 tem formulário web de consulta por CPF/CNPJ; TRF5 tem portal próprio de RPV/precatório.
- **Credencial:** nenhuma API pública documentada foi encontrada em nenhum dos seis. São formulários HTML para consulta humana no navegador; alguns exigem login com MFA só para operações de advogado (cadastrar requisição), não para consulta simples.
- **Natureza:** oficial, mas sem API — acesso programático dependeria de convênio institucional formal com cada tribunal ou de scraping, o que o próprio projeto já veda por princípio (ver seção de segurança do README).
- **Dificuldade:** alta, por tribunal (são 6 sistemas diferentes, sem padronização).
- **Prioridade:** baixa/média, e só individualmente — priorize o TRF onde você já tem processo ativo (ex.: TRF1, pelo caso SINDJUS/DF) e considere buscar contato institucional formal antes de qualquer integração técnica.

## Tribunais estaduais/TJs

- **Busca aceita:** mesma lógica dos TRFs, multiplicada por 27 estados — cada TJ tem seu próprio sistema (e-SAJ, PJe, Projudi, sistemas próprios) e seu próprio módulo de precatórios.
- **Credencial:** varia por tribunal; nenhum padrão nacional.
- **Natureza:** oficial, sem API unificada.
- **Dificuldade:** alta, caso a caso.
- **Prioridade:** baixa por padrão. Só vale a pena construir conector para um TJ específico quando houver um caso/negócio concreto que justifique (ex.: um precatório estadual específico em negociação).

---

## Resumo de prioridade recomendada

1. **Judit** — contratar/solicitar trial agora; conector já preparado no código com header `api-key`.
2. **Escavador** — avaliar como complemento, sem urgência.
3. **SisPreq/PDPJ** — acompanhar evolução institucional; não force conector sem API aberta.
4. **TRF do caso ativo (ex.: TRF1)** — buscar contato institucional formal antes de codar.
5. **Jusbrasil, CJF, demais TRFs/TJs** — avaliar sob demanda, conforme necessidade real de um caso específico.

Nenhum destes conectores foi alterado no código nesta entrega. Este documento é só para orientar a decisão de qual credencial buscar primeiro.
