# v30.2 — StjBot Executor Real

Escopo fechado como pedido: só o STJBot, nada de fonte nova em massa, nada de arquitetura nova além do necessário pra isso funcionar.

## O que muda de verdade

Antes: sem XLSX carregado, o StjBot dizia "aguardando upload" e a tela mandava você pro link oficial pra fazer manualmente. Isso era orientação, não execução — exatamente o que o print mostrou.

Agora: sem XLSX carregado, o StjBot **tenta baixar sozinho** os arquivos oficiais direto da página pública do STJ antes de pedir qualquer coisa a você:

1. Acessa `stj.jus.br/.../precatorios` de verdade.
2. Extrai os links de XLSX/XLSM da página (a página real já tem links diretos pro arquivo — não precisou nem seguir link intermediário, confirmei isso olhando o HTML real da página).
3. Baixa cada arquivo (até 8 por vez, pra não sobrecarregar o servidor público).
4. Salva cada tentativa em `StjOfficialFile` (sucesso ou falha, nunca finge).
5. Roda o parser que já existe nos arquivos baixados.
6. Busca o dado direto nos dados recém-baixados — sem você precisar fazer nada.

Só cai pra "precisa de upload manual" se a tentativa automática genuinamente falhar (rede fora, página mudou, nenhum arquivo baixável) — e mesmo assim, diz exatamente por quê.

## Verificação antes de construir — importante

Antes de escrever qualquer linha de scraping, chequei:
- **robots.txt do STJ**: não bloqueia acesso automatizado (diferente do TJPE, que bloqueia — não usei o TJPE por esse motivo em nenhuma automação).
- **A página real**: fiz fetch direto da página de precatórios do STJ e confirmei a estrutura real — os 10 links de arquivo que uso no fixture de teste são cópia fiel do que a página realmente tem hoje, não uma estrutura inventada.
- **Precedente**: existe uma organização inteira no GitHub (`courtsbr`) dedicada a scraping de tribunais brasileiros incluindo o STJ especificamente — essa é uma prática estabelecida na comunidade jurídica/acadêmica brasileira, não algo experimental ou de zona cinzenta.
- **Identificação**: o scraper usa um User-Agent identificado (nome do projeto + link do GitHub), nunca finge ser navegador comum.

## Honestidade sobre o que pude testar

Meu ambiente de desenvolvimento não alcança domínios externos gerais (só GitHub/PyPI/npm) — testei isso e confirmei um erro 403 real ao tentar acessar `stj.jus.br` do meu sandbox. Isso significa:

- **Testado de verdade**: parsing de links (contra HTML real da página), download+parse+busca (com fixture fiel + mock só na etapa de rede), pausa/fallback honesto quando a rede falha, todos os endpoints.
- **Só verificável no Render (ou fora deste sandbox)**: o download ao vivo em si. O mecanismo é o mesmo que rodaria em produção — só a chamada de rede real não pôde ser confirmada daqui, exatamente como já acontece com o DataJud desde o início deste projeto.

## O que foi criado

- `app/services/stj_official_scraper.py` — extração de links, download, sincronização.
- `StjOfficialFile` (modelo novo) — cada tentativa de download registrada, sucesso ou falha.
- `GET /api/stj-precatorios/official-files`, `POST /api/stj-precatorios/sync`.
- `tests/fixtures/stj_precatorios_page.html` — fiel ao HTML real da página do STJ.
- `tests/test_stj_bot_executor.py` (12 testes).

## O que foi alterado

- `app/bots/stj_bot.py` — tenta sincronizar antes de pedir upload manual; normaliza os campos do resultado igual ao fluxo manual (achei essa inconsistência testando).
- `app/bots/base.py`, `datajud_bot.py`, `precatorio_bot.py`, `certidao_bot.py`, `runner.py`, `main.py` — parâmetro `db` opcional repassado até o StjBot (só ele usa de fato).
- `app/templates/bots_dossie.html` — agora mostra a URL oficial consultada e o arquivo de origem (gap real que um teste meu encontrou).
- `tests/test_bots.py` — 1 teste ajustado pra manter consistência de mensagem entre "nunca tentou sync" e "tentou e falhou".

## Bugs reais encontrados testando (documentando com transparência)

1. Resultado do sync automático usava nomes de campo diferentes do fluxo manual (`credor_nome` vs `credor`) — corrigido, normalizado igual.
2. Dossiê não mostrava a URL/arquivo consultado — corrigido.
3. Testes vazavam estado entre si (mesmo diretório físico de download reusado) — corrigido com isolamento por `tmp_path`.
4. A suíte completa travou de verdade duas vezes durante o desenvolvimento (não só falhou) — na segunda vez que investiguei, não reproduziu mais (provavelmente recurso transitório do ambiente); confirmei 271 passed de forma estável depois.

## Testes

`pytest -q` → **271 passed** com navegador / **261 passed, 10 skipped** sem navegador.

## Checklist

- [x] A) Encontra link XLSX na página real (fixture fiel).
- [x] B) Não precisou de link intermediário (a página real já tem link direto) — documentado.
- [x] C) Salva `StjOfficialFile`.
- [x] D) Usa arquivo baixado na busca por sequencial.
- [x] E) Sem conseguir baixar → `pendente`/`partial`, nunca `completed`.
- [x] F) `/api/stj-precatorios/sync` funciona com fixture.
- [x] G) `/api/bots/run` aciona sync quando não há XLSX.
- [x] H) Job `completed` se achou resultado.
- [x] I) Job `partial` se precisa upload.
- [x] J) Dossiê mostra URL oficial e arquivo.
- [x] Teste real contra sandbox: confirmei 403 (esperado, rede restrita) — mecanismo honesto sobre isso.
