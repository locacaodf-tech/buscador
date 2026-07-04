# Buscador Interno de Processos, Precatórios, RPVs e Certidões

Ferramenta interna de diligência: você digita um dado (CPF, CNPJ, nome, OAB, CNJ, sequencial do STJ ou número de precatório/RPV/requisitório) e ela identifica sozinha o que é, consulta as fontes reais já integradas, e diz em português — sem JSON, sem jargão — o que encontrou, o que ainda falta, e qual a próxima ação.

## Como usar (2 minutos)

1. Acesse a URL publicada (ou rode local, veja abaixo) e faça login com a senha configurada.
2. A tela abre direto no hub: um campo de **Busca livre de diligência** no topo, e 4 botões grandes (Analisar processo por CNJ, Consultar STJ por XLSX/sequencial, Localizar precatório/RPV, Consultar/planejar certidões).
3. Digite qualquer dado na busca livre e toque em "Identificar e buscar" — ela decide sozinha pra onde ir.
4. Toda busca fica salva automaticamente: aparece "Diligência salva nº X" com um botão "Abrir dossiê" (página HTML própria, imprimível). A lista "Últimas diligências" no hub deixa reabrir qualquer uma depois.
5. Toque em "⚙️ Ver se minha ferramenta está pronta" a qualquer momento pra ver o que está configurado (DataJud, STJ, Serpro, banco, login) sem precisar decorar nada técnico.

## O que funciona de verdade hoje, sem depender de provider pago nenhum

- **CNJ** → consulta a API pública do DataJud/CNJ (chave pública oficial já embutida no código), infere o tribunal certo a partir do próprio número (não fica testando os 6 TRFs à toa).
- **STJ** → você sobe o XLSX oficial de precatórios do STJ, e busca por sequencial, número de processo **ou nome do credor/beneficiário** — tudo dentro do arquivo real que você carregou, nunca inventado.
- **Precatório/RPV/requisitório** → gera um plano operacional: quais fontes já dá pra consultar automaticamente, quais exigem credencial, quais exigem consulta manual, e o que falta informar.
- **Certidões** → planejamento por UF/tipo (cível, criminal, Receita/PGFN, trabalhista), sempre dizendo se é automatizado, configurável ou manual — nunca finge "nada consta" sem certidão real.
- **Evidência manual** → cola texto encontrado por fora ou anexa PDF/print/XLSX, vinculado à diligência.
- **CPF/CNPJ/OAB isolados** (sem CNJ, sem nome, sem mais nenhum dado) → a ferramenta é honesta: não existe fonte nacional gratuita pra isso hoje, e ela explica isso claramente em vez de fingir que pesquisou. Fica pronta pra plugar um provider comercial no futuro (`app/services/providers/base.py`), mas isso é opcional, nunca obrigatório.

## Arquitetura por trás da busca livre

```text
Tela (busca livre) ou qualquer outro cliente
  -> POST /api/diligencia
      -> app/services/diligencia_engine.py (identifica tipo, decide o que consultar)
          -> DataJud (CNJ) | STJ XLSX (sequencial/processo/nome) | plano de precatório | plano de certidões
      -> salva em DiligenciaLog
      -> devolve resposta humana + diligencia_id
```

Endpoints do motor:

- `POST /api/diligencia` — ponto único de entrada (o que a busca livre da tela chama).
- `GET /api/diligencias` — lista as últimas diligências salvas.
- `GET /api/diligencias/{id}` — reabre uma diligência com todo o detalhe.
- `GET /api/diligencias/{id}/dossie` — dossiê em HTML, imprimível.
- `GET /api/diagnostico` — o que está configurado (sem expor nenhuma chave).

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

## Camada mais técnica (Modo Avançado da tela / uso direto da API)

Tudo abaixo continua existindo e funcionando — é o que a busca livre e os 4 botões usam por baixo. Fica disponível também pra quem quiser usar a API diretamente (scripts, outra IA, integração futura), sem precisar passar pela tela.

### Ajuste central da API de busca (histórico do projeto)

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

## Limitação essencial

A API Pública do DataJud não é uma API aberta de busca por CPF/nome de parte nem possui campo universal de número de requisitório/precatório/RPV. Ela é muito útil para número CNJ, metadados e movimentações públicas.

Portanto, a estratégia correta é:

- **número CNJ / processo no padrão CNJ**: DataJud;
- **CPF, CNPJ, nome e OAB**: API privada licenciada ou integração oficial com credenciais;
- **número de requisitório, precatório ou RPV**: SisPreq/PDPJ, CJF/TRF, portal/API específica do tribunal ou provedor privado que aceite esse identificador;
- **número desconhecido**: o sistema classifica como `unknown` e tenta apenas conectores que declarem suporte.

## Fluxo de busca do `/api/search` (mais granular, por trás do `/api/diligencia`)

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

## V8 — Raio-X Processual e Fontes Oficiais de Precatórios/LOA

Esta seção documenta uma camada mais antiga do projeto (v8), que continua existindo e funcionando — não foi removida. Ela adiciona a arquitetura de camadas para não confundir **indício processual via DataJud** com **confirmação oficial de precatório/RPV/LOA**.

Endpoints protegidos pelo mesmo mecanismo de autenticação interna:

- `GET /api/official-precatorio/sources` — matriz de fontes oficiais/institucionais mapeadas.
- `POST /api/official-precatorio/plan` — plano de busca por camadas para chegar a precatório/RPV/LOA.
- `POST /api/dossier` — combina a busca processual existente com o plano oficial de precatório/orçamento numa resposta só, em JSON. **Não confundir** com o dossiê da v29 (`GET /api/diligencias/{id}/dossie`, com "ê"), que é uma página HTML de uma diligência já salva no banco — são dois recursos diferentes que coexistem.

Documento principal: `docs/RAIO_X_PRECATORIOS_ARQUITETURA.md`.

Exemplo:

```bash
curl -s -X POST http://127.0.0.1:8000/api/official-precatorio/plan \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: defina_um_token" \
  -d '{"search_type":"cnj","search_key":"0032681-47.2017.4.01.3400","extra_params":{"tribunal":"TRF1","ano_orcamento":"2026"}}'
```
