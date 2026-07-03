from __future__ import annotations

import csv
import io
import re
from typing import Any

import httpx

from .base import BaseConnector, ConnectorCapability, ConnectorError, SearchNotSupported
from ..utils.cnj import normalize_cnj  # noqa: F401  (mantido por simetria com os outros conectores; não usado aqui)

# Fonte oficial verificada ao vivo em 01/07/2026:
# https://www.gov.br/planejamento/pt-br/assuntos/orcamento/precatorios-content/painel-precatorios/dados-abertos
# Nota Metodológica oficial (SOF/MPO) confirma os campos exatos do CSV:
# https://www.gov.br/planejamento/pt-br/assuntos/orcamento/precatorios-content/painel-precatorios/paper-dados-historico-de-precatorios-e-rpvs.pdf
MPO_SIOP_CSV_URL_TEMPLATE = 'https://www1.siop.planejamento.gov.br/siopdoc/lib/exe/fetch.php/dados_abertos:sentencas:expedidos_{ano}.csv'
MPO_SIOP_ANOS_DISPONIVEIS = tuple(range(2007, 2028))  # confirmado ao vivo: um arquivo por exercício, 2007 a 2027

# Nomes de coluna EXATOS da Nota Metodológica oficial — não inferidos, copiados do documento.
COL_CHAVE = 'Chave'
COL_EXERCICIO = 'Exercício'
COL_COD_TRIBUNAL = 'Código do Tribunal'
COL_NOME_TRIBUNAL = 'Nome do Tribunal'
COL_TRIBUNAL_EXPEDIDOR = 'Tribunal Expedidor'
COL_DATA_AJUIZAMENTO = 'Data de Ajuizamento da Ação Originária'
COL_DATA_AUTUACAO = 'Data da Autuação'
COL_TIPO_DESPESA = 'Tipo de Despesa'
COL_COD_UO_EXECUTADA = 'Código da UO Executada'
COL_NOME_UO_EXECUTADA = 'Nome da UO Executada'
COL_NATUREZA_DESPESA = 'Natureza da Despesa'
COL_TIPO_CAUSA = 'Tipo de Causa'
COL_VALOR_ORIGINAL = 'Valor Original do Precatório'
COL_VALOR_ATUALIZADO = 'Valor Atualizado'

TIPO_DESPESA_LABELS = {
    '11': 'Natureza alimentícia - salários, vencimentos, proventos, pensões',
    '12': 'Natureza alimentícia - benefícios previdenciários e indenizações por morte/invalidez',
    '13': 'Natureza alimentícia (acidentário) - benefício previdenciário por acidente de trabalho',
    '14': 'Natureza alimentícia - demais',
    '21': 'Natureza não alimentícia',
    '31': 'Desapropriações - único imóvel residencial do credor',
    '39': 'Desapropriações - demais',
    '41': 'Fundef',
    '99': 'Precatórios sem parcelamento - exercícios anteriores',
}

ESFERA_POR_PREFIXO = {
    '10': 'STF', '11': 'STJ', '12': 'Justiça Federal', '13': 'Justiça Militar da União',
    '14': 'Justiça Eleitoral', '15': 'Justiça do Trabalho',
    '16': 'Justiça Estadual (TJDFT)', '17': 'Justiça Estadual (consolidado via CNJ)',
}


def _parse_valor_br(raw: str | None) -> float | None:
    if raw is None or raw.strip() == '':
        return None
    s = raw.strip().replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


def _norm_text(s: Any) -> str:
    return str(s or '').strip().lower()


def esfera_da_justica(codigo_tribunal: str | None) -> str | None:
    if not codigo_tribunal:
        return None
    prefixo = str(codigo_tribunal)[:2]
    return ESFERA_POR_PREFIXO.get(prefixo)


def normalize_mpo_row(row: dict[str, str], ano_arquivo: int) -> dict[str, Any]:
    """Converte uma linha do CSV oficial (colunas exatas da Nota Metodológica)
    para o formato interno. Campo ausente vira None — nunca inventado."""
    codigo_tribunal = (row.get(COL_COD_TRIBUNAL) or '').strip() or None
    tipo_despesa = (row.get(COL_TIPO_DESPESA) or '').strip() or None
    return {
        'chave': (row.get(COL_CHAVE) or '').strip() or None,
        'exercicio': int(row[COL_EXERCICIO]) if (row.get(COL_EXERCICIO) or '').strip().isdigit() else ano_arquivo,
        'codigo_tribunal': codigo_tribunal,
        'nome_tribunal': (row.get(COL_NOME_TRIBUNAL) or '').strip() or None,
        'tribunal_expedidor': (row.get(COL_TRIBUNAL_EXPEDIDOR) or '').strip() or None,
        'esfera_justica': esfera_da_justica(codigo_tribunal),
        'data_ajuizamento': (row.get(COL_DATA_AJUIZAMENTO) or '').strip() or None,
        'data_autuacao': (row.get(COL_DATA_AUTUACAO) or '').strip() or None,
        'tipo_despesa_codigo': tipo_despesa,
        'tipo_despesa_label': TIPO_DESPESA_LABELS.get(tipo_despesa) if tipo_despesa else None,
        'entidade_devedora_codigo': (row.get(COL_COD_UO_EXECUTADA) or '').strip() or None,
        'entidade_devedora': (row.get(COL_NOME_UO_EXECUTADA) or '').strip() or None,
        'natureza_despesa': (row.get(COL_NATUREZA_DESPESA) or '').strip() or None,
        'tipo_causa': (row.get(COL_TIPO_CAUSA) or '').strip() or None,
        'valor_original': _parse_valor_br(row.get(COL_VALOR_ORIGINAL)),
        'valor_atualizado': _parse_valor_br(row.get(COL_VALOR_ATUALIZADO)),
        'fonte_url': MPO_SIOP_CSV_URL_TEMPLATE.format(ano=ano_arquivo),
        'ano_arquivo': ano_arquivo,
    }


def parse_mpo_csv_text(text: str, ano_arquivo: int) -> list[dict[str, Any]]:
    """Parseia o CSV oficial (';' como separador, decimal com vírgula —
    confirmado ao vivo no arquivo de índice IPCA do mesmo domínio)."""
    reader = csv.DictReader(io.StringIO(text), delimiter=';')
    return [normalize_mpo_row(row, ano_arquivo) for row in reader]


class MpoSiopPrecatoriosConnector(BaseConnector):
    """Dados abertos de precatórios expedidos — Secretaria de Orçamento
    Federal (SOF/MPO), publicados via SIOP.

    Fonte pública confirmada ao vivo em 01/07/2026: CSV por exercício
    (2007-2027), download direto, sem login/captcha
    (https://www.gov.br/planejamento/.../painel-precatorios/dados-abertos).
    Os nomes de coluna usados aqui são copiados literalmente da Nota
    Metodológica oficial do SOF/MPO (link no topo do arquivo) — não
    inferidos por heurística como no conector do STJ.

    LIMITAÇÃO REAL E IMPORTANTE: esta base NÃO tem número de processo/CNJ
    nem nome do credor — por exigência da própria LDO, os dados são
    transmitidos à SOF "sem qualquer dado que possibilite a identificação
    dos respectivos beneficiários". Ou seja, este conector NÃO serve para
    achar "o meu precatório" — serve para confirmar, por entidade devedora
    e exercício, quantos precatórios foram expedidos e o valor agregado
    (a pergunta "está incluído no orçamento de determinado ano?").

    Aviso de honestidade técnica: os arquivos reais (um por ano) passam de
    20MB — maiores que o limite da minha ferramenta de pesquisa, então não
    consegui abrir um e inspecionar linha a linha. A estrutura de colunas
    veio da Nota Metodológica oficial (alta confiança), mas o parser em si
    foi validado só com CSV sintético usando essas colunas — não contra o
    arquivo real. Rode uma consulta real no seu ambiente e me avise se
    algum campo vier vazio que não deveria.
    """

    name = 'mpo_siop_precatorios'
    capabilities = (
        ConnectorCapability(
            'entidade_devedora',
            description='Lista precatórios federais expedidos por entidade devedora num exercício (ex.: "está incluído no orçamento?").',
            required_fields=('search_key (nome ou trecho do nome da entidade devedora)',),
            optional_fields=('extra_params.ano_orcamento (obrigatório na prática — escolhe o arquivo)', 'extra_params.tipo_despesa'),
        ),
    )

    def __init__(self):
        self._csv_cache: dict[int, list[dict[str, Any]]] = {}

    async def search(self, search_type: str, search_key: str, **kwargs: Any) -> list[dict]:
        if search_type not in {'entidade_devedora', 'unknown'}:
            raise SearchNotSupported(
                'MPO/SIOP: esta fonte não tem número de processo/CNJ nem nome de credor (por exigência legal da LDO). '
                'Só busca por entidade devedora (search_type="entidade_devedora") dentro de um exercício. '
                'Para achar um precatório específico, use TRF1 (cjf_trf_precatorios) ou STJ (stj_precatorios).'
            )
        entidade = (search_key or '').strip()
        if not entidade:
            raise SearchNotSupported('MPO/SIOP: informe ao menos parte do nome da entidade devedora.')

        extra = kwargs.get('extra_params') or {}
        ano = extra.get('ano_orcamento')
        if not ano:
            raise SearchNotSupported(
                'MPO/SIOP: informe extra_params.ano_orcamento — cada exercício é um arquivo CSV separado '
                f'(disponíveis: {MPO_SIOP_ANOS_DISPONIVEIS[0]}-{MPO_SIOP_ANOS_DISPONIVEIS[-1]}), '
                'baixar todos de uma vez para uma busca sem ano seria pesado demais.'
            )
        try:
            ano_int = int(ano)
        except (TypeError, ValueError):
            raise SearchNotSupported(f'MPO/SIOP: ano_orcamento inválido: {ano!r}.')
        if ano_int not in MPO_SIOP_ANOS_DISPONIVEIS:
            return [{'provider': self.name, 'tribunal': 'MPO/SIOP',
                     'error': f'Ano {ano_int} fora do intervalo publicado ({MPO_SIOP_ANOS_DISPONIVEIS[0]}-{MPO_SIOP_ANOS_DISPONIVEIS[-1]}).'}]

        try:
            records = await self._records_for_year(ano_int)
        except ConnectorError as exc:
            return [{'provider': self.name, 'tribunal': 'MPO/SIOP', 'error': str(exc)}]
        except Exception as exc:
            return [{'provider': self.name, 'tribunal': 'MPO/SIOP', 'error': f'Falha ao consultar MPO/SIOP: {exc}'}]

        tipo_despesa_filtro = extra.get('tipo_despesa')
        alvo = _norm_text(entidade)
        matches = [
            r for r in records
            if alvo in _norm_text(r.get('entidade_devedora'))
            and (not tipo_despesa_filtro or r.get('tipo_despesa_codigo') == str(tipo_despesa_filtro))
        ]

        out = []
        for rec in matches:
            out.append({'provider': self.name, 'tribunal': rec.get('nome_tribunal') or 'MPO/SIOP', 'source': rec, 'raw_hit': rec})
        return out

    async def _records_for_year(self, ano: int) -> list[dict[str, Any]]:
        if ano in self._csv_cache:
            return self._csv_cache[ano]
        url = MPO_SIOP_CSV_URL_TEMPLATE.format(ano=ano)
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            response = await client.get(url)
            if response.status_code >= 400:
                raise ConnectorError(f'MPO/SIOP retornou HTTP {response.status_code} para {url}')
            records = parse_mpo_csv_text(response.text, ano)
            self._csv_cache[ano] = records
            return records


def orcamento_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Resumo agregado (contagem + soma de valores) — útil para responder
    diretamente 'está incluído no orçamento?' sem listar centenas de linhas."""
    total_original = sum(r['valor_original'] for r in records if r.get('valor_original') is not None)
    total_atualizado = sum(r['valor_atualizado'] for r in records if r.get('valor_atualizado') is not None)
    return {
        'total_registros': len(records),
        'soma_valor_original': round(total_original, 2) if records else 0.0,
        'soma_valor_atualizado': round(total_atualizado, 2) if records else 0.0,
    }
