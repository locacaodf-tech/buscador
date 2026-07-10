# Índice Processual Pessoal — Escopado a Entes Públicos

Construído dentro do codebase real deste projeto (não a partir do ZIP de proveniência duvidosa do outro chat). Judit continua fora — nunca esteve neste código pra começar.

## Escopo, exatamente como você pediu

Só vira registro buscável se a publicação for **ação contra ente público** (Estado/Município/União/INSS/Fazenda Pública) **e/ou** tiver sinal de interesse:
- sentença (agora genérico — "sentença", "julgo procedente" — não só os termos trabalhistas específicos que já existiam)
- trânsito em julgado
- RPV / precatório / ofício requisitório
- cálculos homologados / **SECAJ** (adicionei como sinônimo de cálculo judicial)

Testei com publicação genérica sem ente público nem sinal (contrato de aluguel entre particulares) — **não indexa**. Zero leads criados, confirmado.

## O que foi construído

- **Extração de credor** (nome + CPF/CNPJ) — reaproveitando o mesmo padrão de extração já testado, com o cuidado de parar em vírgula OU ponto (testei explicitamente que "Ana Cristina..., CPF 111.222.333-96" não vaza "111" dentro do nome).
- **Hash salgado de CPF/CNPJ** (`INDICE_CPF_HASH_SALT`, com valor de dev por padrão) — busca por documento compara hash, nunca decodifica. Aviso automático em `/api/watchers/status` se o salt padrão ainda estiver em uso.
- **`GET /api/leads/buscar?nome=X&cpf=Y&cnj=Z`** — busca por qualquer um dos três.
- **`POST /api/leads/{id}/remover`** (tira da busca, preserva dado) e **`?hard=true`** (anonimização real: limpa nome, hash, texto da publicação, termos).

## Testado de ponta a ponta com o caso da auditoria anterior

`Ana Cristina Pereira dos Santos, CPF 111.222.333-96` × `Estado de Goiás` × `sentença proferida`:
- Busca por nome → encontra ✅
- Busca por CPF → encontra via hash ✅
- CPF nunca aparece em claro (testei em `/api/leads`, `/api/leads/{id}`, busca, dossiê e CSV) ✅
- Remoção hard → some da busca e limpa os dados internos ✅

## Testes

444 passed (434+10 sem navegador). 14 testes novos específicos deste módulo.

## O que isso não é

Não é o "índice nacional" amplo que existia na outra sessão (que indexava qualquer publicação, mesmo sem relevância pro seu negócio). É um índice pessoal, estreito, só do que interessa: ações contra ente público com sinal de crédito judicial em potencial — a mesma lógica de negócio que já orienta o resto da ferramenta, só que agora também buscável por nome/CPF/CNJ, não só por lista.
