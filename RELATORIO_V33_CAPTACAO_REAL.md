# v33 — Captação Real (TJGO) — Relatório Técnico

## Fase 1 — Investigação real do TJGO (feita antes de qualquer código)

### Fontes testadas

| Fonte | URL | Login? | Captcha? | Resultado |
|---|---|---|---|---|
| Diário da Justiça próprio do TJGO | www.tjgo.jus.br/.../dj-eletronico | — | — | **Descontinuado desde 16/05/2025** — TJGO migrou exclusivamente pro DJEN nacional (confirmado pelo FAQ oficial do próprio TJGO, atualizado em 28/05/2026) |
| Domicílio Judicial Eletrônico (CNJ) | cnj.jus.br/.../domicilio-judicial-eletronico | **Sim** — certificado digital ou conta gov.br (nível prata/ouro) | — | Não acessível sem credencial pessoal |
| Comunica PJe | comunica.pje.jus.br | **Não** — navegável livremente por humano | Não verificado | **robots.txt desautoriza expressamente acesso automatizado** (`ROBOTS_DISALLOWED` testado diretamente) |
| API de submissão do DJEN | comunicaapi.pje.jus.br/api/v1 | **Sim** — usuário/senha institucional do CNJ (Corporativo) | — | Essa API é pra TRIBUNAIS enviarem publicações, não pra consultar — exige credencial institucional que não temos |
| PJD/Projudi TJGO (consulta processual) | projudi.tjgo.jus.br | Varia | Não em 2025+ | É consulta de PROCESSO JÁ CONHECIDO (por número), não varredura de publicações por palavra-chave — não serve pra descobrir leads novos |

### Conclusão da investigação — direta, sem meio-termo

**Não existe hoje uma forma de automatizar a captura de publicações do TJGO sem violar robots.txt ou sem uma credencial institucional que você não tem.** Isso não é limitação técnica minha — é uma regra explícita do próprio site (`Disallow`) e uma decisão institucional do CNJ (login obrigatório pro Domicílio Judicial Eletrônico). Testei de verdade, não presumi.

O Comunica PJe é **navegável por você livremente, sem login** — a barreira não é acesso, é automação. Por isso a entrega desta rodada é o **importador real**, não um scraper: você (ou alguém do seu time) navega no Comunica PJe como qualquer pessoa, copia o texto da publicação relevante, e cola na ferramenta.

## O que foi construído

### `POST /api/watchers/import-publications`
Aceita texto colado solto (divide automaticamente se houver mais de uma publicação separada por linha em branco dupla) ou lista estruturada. Usa a **mesma esteira** do Publication Watcher: publicação → sinal → lead → dossiê → (bots sob demanda).

**Achados reais corrigidos nesta rodada** (iam impedir exatamente o caso TJGO/Estado de Goiás/Horas Extras de funcionar):
1. O Publication Watcher só extraía CNJ de um campo `numero_processo` separado — nunca do texto livre colado. Corrigido reaproveitando o extrator já testado do IntakeBot.
2. `ente_devedor` tinha o mesmo bug de truncamento já corrigido na v32.2 ("Estado de", não "Estado de Goiás") — só que duplicado aqui no motor de sinais do watcher. Corrigido reaproveitando a versão única e já corrigida.
3. `tipo_acao` nunca era extraído pelo watcher (só pelo IntakeBot). Corrigido.
4. A mensagem de próxima ação não reconhecia `credito_judicial_potencial` como sinal válido, caindo no genérico "sinal fraco" mesmo pontuando como prioridade média. Corrigido, com mensagem rica usando o ente devedor e tipo de ação.

### `GET /api/leads/export.csv`
Data, fonte, tribunal, CNJ, ente devedor, tipo de ação, sinal, prioridade, score, trecho (mascarado), próxima ação, link do dossiê.

### Tela "Captação TJGO"
Dentro do painel "Leads encontrados" — explica com todas as letras a limitação do robots.txt, campo pra colar publicação, botão de exportar CSV.

## Caso real obrigatório — confirmado de ponta a ponta

Colando exatamente:
```
📄 Processo: 5419330-39.2022.8.09.0128
📌 Polo Passivo: Estado de Goiás
📌 Tipo de ação: Horas Extras
```
Resultado: CNJ ✅, TJGO ✅, Estado de Goiás (completo) ✅, Horas Extras ✅, lead criado ✅, bots acionáveis ✅, dossiê abre ✅, CSV exporta com tudo ✅, sem duplicar ✅.

## Testes

`pytest -q` → **430 passed** com navegador / **420 passed, 10 skipped** sem navegador. Confirmado do ZIP extraído do zero.

## O que NÃO está pronto, com honestidade

- **Captura automática diária do TJGO**: não existe, e não vou fingir que existe. Bloqueio documentado: robots.txt do Comunica PJe.
- **TJSP, TRT10, TRF1, DEJT**: mesma investigação precisa ser feita antes de prometer qualquer coisa — não presumi que teriam o mesmo resultado do TJGO.
- **Cron diário**: endpoint pronto (`POST /api/watchers/import-publications` ou `/api/watchers/run`), mas precisa de cron externo (cron-job.org) — sem isso, só roda quando você clicar ou colar.
