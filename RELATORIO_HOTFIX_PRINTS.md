# Hotfix — correção dos 8 erros reais dos prints

Escopo fechado, como pedido: nenhuma fonte nova, nenhum robô, nenhuma arquitetura nova. Só os erros reportados — mais um bug real que apareceu testando a correção.

## Checklist print por print

1. **Campo CNJ aceitava "Paulo Henrique"** → corrigido. Validação client-side (20 dígitos) antes de qualquer chamada ao backend. Texto não-CNJ mostra "Este campo aceita apenas número CNJ... use a Busca livre" + botão "Ir para busca livre" que já leva o valor digitado. Testado.

2. **CNJ válido sem detalhe nenhum** → corrigido. Agora sempre mostra: CNJ digitado, CNJ normalizado, tribunal provável, fonte consultada, data/hora, status da consulta, próxima ação — nos 3 cenários (falhou / consultado sem resultado / encontrado). Testado com CNJ federal (TRF1) e estadual (TJPB).

3. **3 situações misturadas** → corrigidas e distintas: "CNJ inválido" (nem chega no backend agora), "consultado sem resultado" (mensagem específica) e "não foi possível consultar" (falha de rede/API, mensagem diferente). Testado.

4. **Linguagem técnica nas certidões** → removida: `nao_integrado`, `requer_api_contratada`, `captcha_relay.py` e nomes de variável de ambiente (`SERPRO_CND_CONSUMER_KEY/SECRET`) não aparecem mais em nenhuma mensagem. Testado.

5. **Certidão fiscal confusa (Regularize vs Loja Serpro)** → separado: link principal agora é o Regularize (emissão manual grátis), Loja Serpro aparece como link secundário rotulado "Contratar API Serpro para automação futura". Testado, inclusive na tela.

6. **TJPE com nota de pesquisa interna vazando** → substituída por mensagem consciente de captcha, generalizada pra qualquer fonte marcada com captcha (não só TJPE): "O portal do [órgão] exige captcha/validação manual. Por enquanto, emita manualmente pelo link oficial. Depois, registre o resultado como evidência manual." Testado.

7. **"ano_orcamento" cru na tela** → trocado por "ano-orçamento (exercício da LOA)" e "tribunal (qual TRF/TJ)" — sem underscore, sem barra técnica, em qualquer lugar que a lista de campos faltantes apareça. Testado.

8. **STJ mostrado como automático sem XLSX carregado** → corrigido: o plano de precatório agora consulta o diagnóstico real (`/api/diagnostico`) e só classifica o STJ como "já dá pra consultar agora" se o arquivo estiver de fato carregado nesta sessão. Sem arquivo, aparece como "disponível após carregar o XLSX oficial" com botão direto "Ir para upload STJ". Testado nos dois estados (sem e com arquivo).

9. **Dossiê/histórico só na busca livre** → agora **todos os 4 fluxos dedicados** (CNJ, STJ, Precatório/RPV, Certidões) salvam a diligência e mostram "✅ Diligência salva nº X" + "Abrir dossiê →", além de atualizar "Últimas diligências". Testado com múltiplas diligências de tipos diferentes acumulando na lista.

## Bug real encontrado testando (não estava nos prints)

Ao alternar entre Modo Avançado (STJ) e voltar pro Modo Simples depois de já ter navegado por um painel (ex.: Precatório/RPV), o hub principal ficava **invisível** — `setMode()` só trocava a classe do body, mas não desfazia o `style="display:none"` que `mostrarPainel()` grava direto no elemento (que tem prioridade sobre a classe). Corrigido: voltar pro modo simples agora sempre garante que o hub apareça. Sem esse fix, eu não conseguiria nem confirmar o item 8 corretamente — foi um bug bloqueador real.

## Testes

`pytest -q` → **218 passed** com navegador / **212 passed, 6 skipped** sem navegador (os 6 de sempre, `captcha_relay`). Confirmado dos dois jeitos.

Arquivo dedicado: `tests/test_hotfix_persistencia_e_tribunal.py` (8 testes) cobre inferência de tribunal (federal + estadual) e persistência nos 4 fluxos dedicados.

## Arquivos alterados

- `app/utils/cnj.py` — `infer_tribunal_from_cnj()` (federal + estadual, tabela oficial do CNJ).
- `app/connectors/datajud.py` — usa a inferência ampla; mensagem de erro sem citar provedor por nome.
- `app/services/diligencia_engine.py` — `_consultar_cnj` agora sempre inclui tribunal provável, status da consulta e distingue os 3 cenários.
- `app/services/certificate_center.py` — Serpro sem vazar variável de ambiente, link principal corrigido (Regularize); mensagem de captcha generalizada (não só TJPE).
- `app/services/official_precatorio_sources.py` — campos faltantes em linguagem humana.
- `app/main.py` — `_salvar_diligencia()` (ponto único de persistência) usado por CNJ, STJ, Precatório e Certidões.
- `app/templates/index.html` — validação de CNJ, exibição completa de detalhes, categorização real do STJ no plano, "Diligência salva"/"Abrir dossiê" nos 4 fluxos, correção do bug de navegação `setMode()`.
- `tests/test_datajud_connector.py`, `tests/test_certificate_center.py`, `tests/test_official_precatorio_sources.py` — atualizados pra nova linguagem/comportamento.
- `tests/test_hotfix_persistencia_e_tribunal.py` — novo.

## O que não fiz (fora de escopo, por acordo)

Nenhuma fonte nova, nenhum robô, nenhuma fila de jobs, nenhuma automação de portal nova. Isso é hotfix, não v30.
