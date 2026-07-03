# Certidões cível/criminal — os 27 Tribunais de Justiça estaduais

Pesquisa real (busca + fetch), não presumida, feita em 02/07/2026. Nível de profundidade varia por estado — marcado explicitamente onde só confirmei a URL oficial (via documento da ANTT, que lista os 27 links pra fins de habilitação de motorista) sem detalhar os campos exatos do formulário.

## Achados que mudam a estratégia de automação

1. **Captcha clássico confirmado de verdade: TJPE.** A página de antecedentes criminais retorna a mensagem real "Imagem de segurança digitada incorretamente" quando o código está errado — exatamente o padrão que o `captcha_relay.py` (da entrega anterior) resolve. **Este é o primeiro alvo real pra esse mecanismo.**
2. **8 estados usam a mesma plataforma (SAJ, da Softplan), no padrão `esaj.tj{uf}.jus.br/sco/abrirCadastro.do`**: AC, AL, AM (variante `consultasaj`), BA, MS, RN, SC, SP. Mesma plataforma provavelmente significa mesmo formulário — vale a pena estudar uma a fundo (sugiro BA ou SP) e aplicar o aprendizado às outras 7.
3. **Essa mesma plataforma SAJ bloqueia acesso automatizado via `robots.txt`** (confirmei tentando abrir `esaj.tjba.jus.br` — recusado). Isso é uma barreira **antes mesmo do captcha**: mesmo sem captcha, automatizar contra esses 8 estados desrespeitaria o `robots.txt`, que o projeto trata como linha vermelha da mesma forma que trata captcha.
4. **SP e SC exigem conta gov.br nível prata/ouro** nos sistemas mais novos (`certidoes.tjsp.jus.br`, `certidoes.tjsc.jus.br`) — isso é uma barreira de identidade, não um captcha, mas também impede automação simples (a conta gov.br é pessoal, verificada, não dá pra ter uma "conta de robô").
5. **Encontrei vários sites terceiros cobrando por algo que é gratuito** ("Sistema Federal", "Sistema Central", "Central de Cartórios") aparecendo nos resultados de busca pra MG, RJ, TJMG — nenhum deles é oficial. Certidão judicial gratuita é regra desde a ADI 3.278/CNJ; qualquer cobrança fora de taxa de licitação/2ª via específica é suspeita.
6. **Padrão de campos muito consistente onde consegui confirmar**: nome completo, CPF (e/ou CNPJ para PJ), RG, data de nascimento, nome da mãe (e às vezes do pai), e-mail. Alguns pedem naturalidade. Nenhum pediu endereço completo, exceto casos pontuais.
7. **Vários tribunais só emitem automaticamente quando o resultado é "NADA CONSTA"** — se há qualquer ocorrência (inclusive risco de homônimo), o pedido cai para análise manual/presencial. Isso limita o valor de qualquer automação: ela resolve o caso mais comum (nada consta), não o caso que você mais provavelmente quer conferir (que há processo).

## Tabela completa

| UF | Órgão | URL oficial | Plataforma | Gratuito | Particularidade |
|---|---|---|---|---|---|
| AC | TJAC | esaj.tjac.jus.br/sco/abrirCadastro.do | SAJ | provável | mesma plataforma de SP/BA — não verificado a fundo |
| AL | TJAL | www2.tjal.jus.br/sco/abrirCadastro.do | SAJ | provável | idem |
| AP | TJAP | tucujuris.tjap.jus.br/.../certidao-publica | própria (Tucujuris) | não verificado | |
| AM | TJAM | consultasaj.tjam.jus.br/sco/abrirCadastro.do | SAJ | provável | |
| BA | TJBA | esaj.tjba.jus.br/sco/abrirCadastro.do (+ portalcertidoes.tjba.jus.br) | SAJ | sim (confirmado) | **robots.txt bloqueia acesso automatizado** |
| CE | TJCE | sirece.tjce.jus.br/sirece-web/nova/solicitacao.jsf | SIRECE (própria) | sim (confirmado) | também via app "TJCE Mobile" |
| DF | TJDFT | tjdft.jus.br/servicos/certidao-nada-consta | própria | não verificado | distrital, não estadual — incluído por já estar mapeado |
| ES | TJES | sistemas.tjes.jus.br/certidaonegativa/... | própria | sim | emissão automática se nada consta |
| GO | TJGO | projudi.tjgo.jus.br/CertidaoNegativaPositivaPublica | PROJUDI | sim | **só emite online se resultado for negativo**; positivo exige presencial |
| MA | TJMA | jurisconsult.tjma.jus.br/#/certidao-generate-state-certificate-form | Jurisconsult | não verificado | |
| MT | TJMT | sec.tjmt.jus.br/emitir-certidao-de-primeiro-grau | própria (SEC) | não verificado | |
| MS | TJMS | esaj.tjms.jus.br/sco/abrirCadastro.do | SAJ | provável | mesma plataforma bloqueada por robots.txt |
| MG | TJMG | rupe.tjmg.jus.br / www8.tjmg.jus.br/certidaoJudicial | RUPE (própria) | sim (confirmado) | nome + CPF/CNPJ (opcional, mas recomendado) |
| PA | TJPA | consultas.tjpa.jus.br/certidao/... | própria | não verificado | |
| PB | TJPB | app.tjpb.jus.br/certo/paginas/publico/areaPublica.jsf | CERTO (própria) | não verificado | |
| PR | TJPR | portal.tjpr.jus.br/portletforms/publico/frm.do?idFormulario=4667 | própria | sim (confirmado — CNJ obrigou até cartórios privados) | PF (criminal/cível/eleitoral/improbidade) e PJ separados |
| PE | TJPE | tjpe.jus.br/antecedentescriminaiscliente + certidoesunificadas.app.tjpe.jus.br | própria | sim | **captcha clássico confirmado**; nome, documento, CPF, título de eleitor, data nasc., nacionalidade, endereço; só emite se "nada consta" |
| PI | TJPI | tjpi.jus.br/themisconsulta/certidao | Themis (própria) | não verificado | |
| RJ | TJRJ | www4.tjrj.jus.br/portal-extrajudicial/certidao/judicial/solicitar (CJE) | própria | sim (confirmado) | nome, CPF, RG, data nasc., nome dos pais; **limite de 10 pedidos/dia por CPF/CNPJ** |
| RN | TJRN | esaj.tjrn.jus.br/sco/abrirCadastro.do | SAJ | provável | mesma plataforma bloqueada por robots.txt |
| RS | TJRS | tjrs.jus.br/novo/.../emissao-de-antecedentes-e-certidoes | própria | sim (confirmado) | eletrônico obrigatório na comarca de Porto Alegre |
| RO | TJRO | webapp.tjro.jus.br/certidaoonline/pages/cnpg.xhtml | própria | não verificado | |
| RR | TJRR | tjrr.jus.br/index.php/certidao-negativa | própria | não verificado | |
| SC | TJSC | esaj.tjsc.jus.br/sco/abrirCadastro.do (antigo) / certidoes.tjsc.jus.br (novo) | SAJ + própria | sim (confirmado) | nome, CPF, RG, órgão expedidor, nome mãe/pai, data nasc., e-mail, telefone, finalidade; **sistema novo exige conta gov.br nível prata/ouro** |
| SP | TJSP | esaj.tjsp.jus.br/sco/abrirCadastro.do (capital) / certidoes.tjsp.jus.br (2ª instância) | SAJ + própria | sim (confirmado) | nome, RG, CPF/CNPJ, nome pai e mãe, data nasc., naturalidade, e-mail; **certidoes.tjsp.jus.br exige conta gov.br nível prata/ouro**; interior varia por comarca |
| SE | TJSE | tjse.jus.br/portal/servicos/judiciais/certidao-online/... | própria | não verificado | |
| TO | TJTO | eproc1.tjto.jus.br/.../acao=cj_online | eproc | não verificado | |

## O que isso muda pra automação (conectado ao captcha_relay já construído)

- **Melhor primeiro alvo real: TJPE.** Confirmei captcha clássico, confirmei os campos, e o mecanismo de pausa-e-retomada já está pronto e testado. Esse é o candidato natural pra validar o `captcha_relay` contra um site de verdade.
- **8 estados na plataforma SAJ (incluindo SP) estão fora de cogitação pra automação de formulário**, porque o `robots.txt` deles proíbe explicitamente — isso é uma linha que o projeto já se comprometeu a não cruzar, junto com captcha e login.
- **SP e SC (sistemas novos) também estão fora**, porque dependem de conta gov.br pessoal verificada — não tem "automatizar" isso de forma responsável.
- Os demais ~17 estados ainda **não tiveram os campos exatos do formulário confirmados** — só a URL. Esse é o próximo passo de pesquisa, se você quiser continuar estado por estado.

## Próximo passo recomendado

1. Implementar de verdade o conector `tjpe_certidoes_browser` usando o `captcha_relay.py` — é o único alvo com captcha clássico confirmado E campos conhecidos.
2. Pra completar o quadro, pesquisar os ~17 estados que ainda não têm campo confirmado (posso continuar nesta mesma sessão se quiser).
3. Estudar a fundo UM formulário da plataforma SAJ (sugiro BA, já que é onde confirmei o bloqueio de robots.txt) — mesmo não podendo automatizar, vale documentar os campos exatos pra pelo menos pré-preencher manualmente mais rápido.
