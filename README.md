# Claude Buscador de Processos

Solução interna para consulta e triagem de processos, precatórios, RPVs e requisitórios.

## Ajuste central desta versão

O sistema **não presume que você sempre buscará por CPF/nome**. Ele aceita um identificador flexível e resolve o melhor caminho conforme o que cada API aceitar.

Identificadores suportados no modelo interno:

- nome da parte;
- CPF;
- CNPJ;
- OAB;
- número CNJ;
- número do processo;
- número do requisitório;
- número do precatório;
- número da RPV;
- varredura geral por indícios de precatório/RPV.

Cada provedor/conector declara suas próprias capacidades em `/api/capabilities`. Isso é essencial porque **as exigências variam por API e por tribunal**. Um tribunal pode exigir CNJ; outro pode exigir CPF do beneficiário; outro pode exigir número do requisitório + ano-orçamento; outro pode exigir autenticação institucional.

## O que esta versão faz

1. Consulta processos por **número CNJ** na API Pública do DataJud/CNJ.
2. Faz varredura por **indícios de precatório/RPV** usando classes, assuntos e movimentos da TPU/SisPreq.
3. Aceita busca livre por CPF, CNPJ, nome, OAB, CNJ, processo, requisitório, precatório ou RPV.
4. Detecta automaticamente o tipo provável do identificador informado.
5. Mantém um registry de capacidades por API/conector.
6. Mantém histórico local em SQLite.
7. Entrega tela simples para uso interno.
8. Deixa conectores prontos para ligar em Judit, Escavador, Jusbrasil, SisPreq/PDPJ, CJF/TRFs e APIs próprias de tribunais quando houver credenciais.

## Limitação essencial

A API Pública do DataJud não é uma API aberta de busca por CPF/nome de parte nem possui campo universal de número de requisitório/precatório/RPV. Ela é muito útil para número CNJ, metadados e movimentações públicas.

Portanto, a estratégia correta é:

- **número CNJ / processo no padrão CNJ**: DataJud;
- **CPF, CNPJ, nome e OAB**: API privada licenciada ou integração oficial com credenciais;
- **número de requisitório, precatório ou RPV**: SisPreq/PDPJ, CJF/TRF, portal/API específica do tribunal ou provedor privado que aceite esse identificador;
- **número desconhecido**: o sistema classifica como `unknown` e tenta apenas conectores que declarem suporte.

## Como rodar localmente

```bash
cd claude-buscador-processos
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Abra:

```text
http://127.0.0.1:8000
```

## Fluxo de busca

```text
Usuário informa o que tem
  -> SearchRequest
      -> identifier resolver
          -> cnj / cpf / cnpj / name / oab / numero_processo / requisitorio_number / precatorio_number / rpv_number / unknown
      -> provider capability registry
          -> escolhe conector compatível
      -> conector da API
      -> normalização
      -> classificador de precatório/RPV
      -> SQLite + resposta JSON
```

## Rotas principais

### GET /api/capabilities

Mostra quais identificadores cada conector aceita e quais campos extras pode exigir.

```bash
curl http://127.0.0.1:8000/api/capabilities
```

### POST /api/search — campo livre automático

```json
{
  "provider": "auto",
  "search_type": "auto",
  "search_key": "0000832-35.2018.4.01.3202",
  "tribunals": ["TRF1"],
  "max_results": 50,
  "precatorio_only": false,
  "include_raw": false
}
```

### POST /api/search — CPF com parâmetros extras

```json
{
  "provider": "auto",
  "search_type": "cpf",
  "search_key": "999.999.999-99",
  "tribunals": ["TRF1", "TRF2"],
  "extra_params": {
    "nome": "NOME DO BENEFICIÁRIO",
    "data_nascimento": "1980-01-01"
  },
  "max_results": 100
}
```

### POST /api/search — número de precatório

```json
{
  "provider": "auto",
  "search_type": "precatorio_number",
  "search_key": "PRC-2027-000000",
  "extra_params": {
    "tribunal": "TRF1",
    "ano_orcamento": 2027,
    "entidade_devedora": "União"
  }
}
```

Nesta versão, esse tipo retornará aviso se nenhum conector oficial de precatórios estiver configurado. O objetivo é deixar o contrato correto para plugar o SisPreq/PDPJ/TRF/TJ depois.

### POST /api/search — varredura de precatório/RPV no DataJud

```json
{
  "provider": "datajud",
  "search_type": "precatorio_scan",
  "tribunals": ["TRF1", "TRF2", "TRF3", "TRF4", "TRF5", "TRF6"],
  "max_results": 100,
  "precatorio_only": true
}
```

## Exemplos de uso via CLI

Busca por número CNJ nos TRFs:

```bash
python cli.py search "0000832-35.2018.4.01.3202" --search-type cnj --provider datajud --tribunals TRF1
```

Busca flexível por CPF via provedor privado, se configurado:

```bash
python cli.py search "999.999.999-99" --search-type cpf --provider auto --tribunals TRF1,TRF2
```

Busca por número de precatório com campos extras:

```bash
python cli.py search "PRC-2027-000000" \
  --search-type precatorio_number \
  --provider auto \
  --extra-params '{"tribunal":"TRF1","ano_orcamento":2027,"entidade_devedora":"União"}'
```

Ver capacidades dos conectores:

```bash
python cli.py capabilities
```

Varredura de precatórios/RPVs nos TRFs:

```bash
python cli.py scan-precatorios --tribunals TRF1,TRF2,TRF3,TRF4,TRF5,TRF6 --max-results 100
```

## Registry de capacidades por conector

### DataJud

Suporta nesta versão:

- `cnj`;
- `numero_processo`, quando o número estiver no padrão CNJ;
- `precatorio_scan`.

Não suporta de forma aberta:

- CPF;
- CNPJ;
- nome;
- OAB;
- número universal de requisitório/precatório/RPV.

### Judit

Autenticação exclusivamente por header `api-key` (nunca `Authorization: Bearer`), configurada via `JUDIT_API_KEY` no `.env`.

Suporta:

- CPF;
- CNPJ;
- nome;
- OAB;
- CNJ.

Não cobre requisitório/precatório/RPV; para isso, use `tribunal_precatorios` quando houver conector real.

### tribunal_precatorios

É um **contrato de integração** para APIs oficiais de precatórios. Ele ainda não faz chamadas reais, mas define o lugar certo para plugar:

- SisPreq/PDPJ;
- CJF;
- TRF1 a TRF6;
- portais estaduais de precatórios;
- integrações próprias de tribunais.

Esse conector deve ser implementado conforme o endpoint real e as exigências de autenticação/campos obrigatórios.

## Como adicionar uma API de tribunal

1. Crie um arquivo em `app/connectors/`, por exemplo `trf1_precatorios.py`.
2. Herde de `BaseConnector`.
3. Declare `capabilities`, informando quais identificadores aceita.
4. Implemente `search()`.
5. Registre o conector em `CONNECTOR_CLASSES` dentro de `app/services/orchestrator.py`.
6. Retorne resultados no formato bruto; o `normalizer` tentará padronizar.

Exemplo conceitual:

```python
class TRF1PrecatoriosConnector(BaseConnector):
    name = 'trf1_precatorios'
    capabilities = (
        ConnectorCapability(
            'precatorio_number',
            required_fields=('search_key', 'extra_params.ano_orcamento'),
            optional_fields=('extra_params.cpf', 'extra_params.entidade_devedora'),
        ),
    )

    async def search(self, search_type: str, search_key: str, **kwargs):
        # montar payload conforme API real do TRF1
        # autenticar
        # chamar endpoint
        # devolver lista de dicts
        return []
```

## Como o score de precatório funciona

A rotina usa sinais de:

- classes: `1265 Precatório`, `1266 Requisição de Pequeno Valor`, `1040 RPV/STJ`, `1677 Precatório/STJ`;
- movimentos: expedição de precatório/RPV, enviada ao tribunal, preparada para envio, paga, cancelada, suspensa etc.;
- assuntos: parte incontroversa, renúncia parcial, competência funcional/precatório;
- textos de classe, assunto e movimento que mencionem precatório/RPV.

O score é apenas triagem. O resultado precisa ser validado no processo, requisitório e portal de precatórios do tribunal.

## Segurança e LGPD

- Use apenas para finalidade legítima da empresa.
- Não exponha CPF, token ou JSON bruto em frontend público.
- Ative `INTERNAL_API_TOKEN` se for publicar em rede interna.
- Guarde logs de consulta com máscara de documento.
- Defina política de retenção e descarte dos dados.
- Não tente contornar captcha, login, segredo de justiça, bloqueio técnico ou regra de uso de portal.

## Próximas integrações recomendadas

1. API privada de processos para CPF/CNPJ/nome/OAB.
2. SisPreq/PDPJ/Codex, se houver credencial/perfil/autorização.
3. CJF/TRFs para precatórios e RPVs federais.
4. APIs próprias de TJs estaduais para precatórios.
5. Monitoramento recorrente por CPF/CNPJ/CNJ e por número de requisitório/precatório/RPV.

## Comando para levar ao Claude

```text
Use este pacote como base. Não reescreva tudo. O ponto central é manter busca por identificadores flexíveis: nome, CPF, CNPJ, OAB, CNJ, número do processo, número do requisitório, número do precatório e número da RPV. Cada conector deve declarar suas capabilities: quais search_types aceita, quais required_fields exige e quais optional_fields aceita. Primeiro rode a aplicação, depois implemente apenas o conector real escolhido para CPF/nome ou para precatórios oficiais, registrando-o em CONNECTOR_CLASSES. Preserve DataJud para CNJ e precatorio_scan.
```

## V8 — Raio-X Processual e Fontes Oficiais de Precatórios/LOA

Esta versão adiciona a arquitetura de camadas para não confundir **indício processual via DataJud** com **confirmação oficial de precatório/RPV/LOA**.

Novos endpoints protegidos pelo mesmo mecanismo de autenticação interna:

- `GET /api/official-precatorio/sources` — matriz de fontes oficiais/institucionais mapeadas.
- `POST /api/official-precatorio/plan` — plano de busca por camadas para chegar a precatório/RPV/LOA.
- `POST /api/dossier` — combina a busca processual existente com o plano oficial de precatório/orçamento.

Documento principal: `docs/RAIO_X_PRECATORIOS_ARQUITETURA.md`.

Exemplo:

```bash
curl -s -X POST http://127.0.0.1:8000/api/official-precatorio/plan \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: defina_um_token" \
  -d '{"search_type":"cnj","search_key":"0032681-47.2017.4.01.3400","extra_params":{"tribunal":"TRF1","ano_orcamento":"2026"}}'
```
