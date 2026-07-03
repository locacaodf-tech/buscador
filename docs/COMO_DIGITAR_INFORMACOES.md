# Como digitar as informações no Buscador

A tela agora tem um **orientador de preenchimento**. Primeiro escolha o tipo de informação e depois digite o valor. O sistema mostra exemplos, valida o formato e normaliza quando for seguro.

## CPF
Pode digitar com ou sem pontuação.

Aceitos:

```text
72137797100
721.377.971-00
```

O sistema envia ao backend apenas os 11 números:

```text
72137797100
```

## CNPJ
Pode digitar com ou sem máscara.

Aceitos:

```text
00000000000191
00.000.000/0001-91
```

O sistema envia ao backend apenas os 14 números.

## OAB
Informe número e UF.

Aceitos:

```text
15547/DF
DF15547
15547 + UF DF selecionada no campo UF
```

O sistema separa automaticamente:

```text
search_key: 15547
extra_params.uf: DF
```

## Número CNJ
Use o número completo do processo.

Aceitos:

```text
0032681-47.2017.4.01.3400
00326814720174013400
```

## Nome
Digite o nome mais completo possível.

Exemplo:

```text
Maria da Silva Souza
```

Para reduzir homônimos, complemente com CPF, UF, data de nascimento ou nome da mãe quando tiver.

## Precatório, requisitório ou RPV
O formato varia por tribunal. Quando tiver, informe também:

- tribunal;
- UF;
- ano-orçamento;
- entidade devedora;
- número do processo de origem;
- CPF/CNPJ do beneficiário, quando a fonte exigir.

## Sequencial STJ
Use o número sequencial da planilha/lista oficial do STJ.

Exemplo:

```text
15547
```

Antes de buscar, carregue o XLSX oficial do STJ na aba **STJ**.

## Regra prática

Se não souber o tipo, escolha:

```text
Não sei / detectar automaticamente
```

O sistema tentará identificar CPF, CNPJ, CNJ, OAB ou nome. Para LOA/orçamento/precatório, quanto mais dados auxiliares você informar, melhor.
