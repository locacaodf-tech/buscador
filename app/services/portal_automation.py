from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class AutomationStatus:
    """Status possíveis de uma tentativa de consulta por automação de navegador."""

    OK = 'ok'
    NOT_FOUND = 'not_found'
    REQUIRES_MANUAL_ACTION = 'requires_manual_action'
    REQUIRES_LOGIN = 'requires_login'
    REQUIRES_CERTIFICATE = 'requires_certificate'
    CAPTCHA_DETECTED = 'captcha_detected'
    RATE_LIMITED = 'rate_limited'
    SOURCE_ERROR = 'source_error'
    NOT_IMPLEMENTED = 'not_implemented'


@dataclass
class AutomationResult:
    status: str
    source_id: str
    fonte_url: str
    consulted_at: str
    fields: dict[str, Any] = field(default_factory=dict)
    raw_html: str | None = None
    raw_json: dict[str, Any] | None = None
    message: str = ''

    def as_dict(self) -> dict[str, Any]:
        return {
            'status': self.status,
            'source_id': self.source_id,
            'fonte_url': self.fonte_url,
            'consulted_at': self.consulted_at,
            'fields': self.fields,
            'raw_html': self.raw_html,
            'raw_json': self.raw_json,
            'message': self.message,
        }


class PortalAutomationConnector(ABC):
    """Base para conectores de automação de navegador (Playwright) em portais públicos.

    POR QUE ISTO É SÓ ARQUITETURA, NÃO CONECTORES FUNCIONANDO:

    Este projeto foi escrito num ambiente sem acesso de rede aos domínios dos
    tribunais — só uma ferramenta de pesquisa web (sem execução de Playwright
    real, sem DOM de verdade). Implementar de fato um destes conectores exige
    abrir o site ao vivo, inspecionar os seletores DOM reais, testar o fluxo
    completo (preencher, clicar, esperar, extrair, lidar com captcha/sessão).
    Nada disso pode ser validado daqui. Publicar um conector "pronto" sem essa
    validação seria inventar que funciona — exatamente o que você pediu para
    nunca fazer. Esta classe define o contrato certo para quando isso for
    implementado, seja por você rodando localmente com acesso real, seja por
    mim numa sessão com esse acesso configurado.

    REGRAS OBRIGATÓRIAS para qualquer implementação concreta:
    - nunca preencher/burlar captcha — se aparecer, parar e retornar CAPTCHA_DETECTED;
    - nunca burlar login — se exigir, parar e retornar REQUIRES_LOGIN;
    - nunca burlar certificado digital — se exigir, parar e retornar REQUIRES_CERTIFICATE;
    - nunca acessar área restrita sem credencial autorizada;
    - respeitar rate limit (min_seconds_between_requests) e usar cache;
    - sempre registrar data/hora (consulted_at) e URL da fonte (fonte_url);
    - guardar raw_html ou raw_json da resposta quando possível;
    - nunca inventar dado — campo não encontrado fica None, não um palpite.
    """

    source_id: str
    fonte_url: str
    min_seconds_between_requests: float = 3.0

    def can_search(self, search_type: str, extra_params: dict[str, Any] | None = None) -> bool:
        """Diz se este conector aceita o tipo de busca e tem os campos mínimos.

        Implementação padrão: False. Cada conector concreto deve declarar
        explicitamente o que aceita — nunca presumir.
        """
        return False

    @abstractmethod
    def build_query(self, search_type: str, search_key: str, extra_params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Monta os parâmetros de navegação: que formulário, que campos
        preencher, com que valores. Não faz nenhuma chamada de rede — só
        descreve a consulta que run_browser_search vai executar."""
        raise NotImplementedError

    @abstractmethod
    async def run_browser_search(self, query: dict[str, Any]) -> Any:
        """Abre o navegador (Playwright), navega, preenche e submete o
        formulário descrito por build_query. Deve chamar detect_blockers()
        antes de preencher qualquer campo sensível, e retornar imediatamente
        se houver bloqueio. Retorna o objeto de página para extract_results
        processar — não retorna dado final aqui."""
        raise NotImplementedError

    @abstractmethod
    def detect_blockers(self, page: Any) -> str | None:
        """Verifica se a página atual tem captcha, exige login ou
        certificado. Retorna um valor de AutomationStatus
        (REQUIRES_LOGIN / REQUIRES_CERTIFICATE / CAPTCHA_DETECTED) ou None
        se não há bloqueio detectado. Deve rodar ANTES de extract_results."""
        raise NotImplementedError

    @abstractmethod
    def extract_results(self, page: Any) -> dict[str, Any]:
        """Lê o HTML/DOM já carregado e devolve um dict bruto (raw), sem
        normalizar. Preserva o HTML original quando possível."""
        raise NotImplementedError

    @abstractmethod
    def normalize_results(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Converte o dict bruto extraído para o formato comum de precatório
        oficial (ver COMMON_OFFICIAL_FIELDS em official_precatorio_sources.py).
        Campo não encontrado vira None — nunca um valor inventado."""
        raise NotImplementedError

    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def not_implemented_result(self) -> AutomationResult:
        return AutomationResult(
            status=AutomationStatus.NOT_IMPLEMENTED,
            source_id=self.source_id,
            fonte_url=self.fonte_url,
            consulted_at=self.now_iso(),
            message=(
                f'{self.source_id}: automação de navegador ainda não implementada de verdade. '
                'Isto é só o contrato/arquitetura (ver docstring da classe) — precisa ser '
                'validado com acesso real ao site antes de virar consulta de verdade.'
            ),
        )


class StubPortalAutomationConnector(PortalAutomationConnector):
    """Stub genérico: declara a fonte (source_id/fonte_url) mas não implementa
    nenhum passo real ainda. Todo método levanta NotImplementedError com uma
    mensagem clara — de propósito, para nunca fingir que a consulta funciona.
    """

    def __init__(self, source_id: str, fonte_url: str, notes: str = ''):
        self.source_id = source_id
        self.fonte_url = fonte_url
        self.notes = notes

    def can_search(self, search_type: str, extra_params: dict[str, Any] | None = None) -> bool:
        return False

    def build_query(self, search_type: str, search_key: str, extra_params: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError(f'{self.source_id}: build_query ainda não implementado. {self.notes}')

    async def run_browser_search(self, query: dict[str, Any]) -> Any:
        raise NotImplementedError(f'{self.source_id}: run_browser_search ainda não implementado. {self.notes}')

    def detect_blockers(self, page: Any) -> str | None:
        raise NotImplementedError(f'{self.source_id}: detect_blockers ainda não implementado. {self.notes}')

    def extract_results(self, page: Any) -> dict[str, Any]:
        raise NotImplementedError(f'{self.source_id}: extract_results ainda não implementado. {self.notes}')

    def normalize_results(self, raw: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(f'{self.source_id}: normalize_results ainda não implementado. {self.notes}')


# Stubs pedidos explicitamente. TRF1 já tem consulta real por CNJ/processo em
# app/connectors/cjf_trf_precatorios.py — SEM navegador, só HTTP direto. Um
# browser automation para TRF1 só faria sentido para CPF/CNPJ/nome/OAB, que
# aquele conector ainda não cobre.
PORTAL_AUTOMATION_STUBS: dict[str, StubPortalAutomationConnector] = {
    'trf1_precatorios_browser': StubPortalAutomationConnector(
        'trf1_precatorios_browser', 'https://processual.trf1.jus.br/consultaProcessual/',
        notes='CNJ/processo já tem conector real sem navegador (cjf_trf_precatorios). Este stub cobriria CPF/CNPJ/nome/OAB.',
    ),
    'trf2_precatorios_browser': StubPortalAutomationConnector(
        'trf2_precatorios_browser', 'https://www10.trf2.jus.br/consultas/precatorio-e-rpv/',
        notes='TRF2 exige login/certificado desde 2024 (segredo de justiça) — automação não contorna isso, só formalizaria o requires_login/requires_certificate.',
    ),
    'trf3_requisicoes_browser': StubPortalAutomationConnector(
        'trf3_requisicoes_browser', 'https://web.trf3.jus.br/consultas/internet/consultareqpag',
    ),
    'trf4_precatorios_browser': StubPortalAutomationConnector(
        'trf4_precatorios_browser', 'https://consulta.trf4.jus.br/trf4/controlador.php?acao=pagina_precatorios',
    ),
    'trf5_precatorios_browser': StubPortalAutomationConnector(
        'trf5_precatorios_browser', 'https://rpvprecatorio.trf5.jus.br/',
    ),
    'trf6_precatorios_browser': StubPortalAutomationConnector(
        'trf6_precatorios_browser', 'https://portal.trf6.jus.br/rpv-e-precatorios/consulta-precatorio-e-rpv/',
    ),
    'tjdft_sapre_browser': StubPortalAutomationConnector(
        'tjdft_sapre_browser', 'https://www.tjdft.jus.br/',
        notes='SAPRE parece ser aplicação com sessão (extensão .xhtml, deu "sessão expirada" numa tentativa de fetch simples) — provável candidato real a precisar de navegador de verdade, não só HTTP direto. URL específica do SAPRE precisa ser reconfirmada antes de implementar.',
    ),
    'tjsp_precatorios_browser': StubPortalAutomationConnector(
        'tjsp_precatorios_browser', 'https://www.tjsp.jus.br/',
        notes='URL específica da página de precatórios do TJSP ainda não confirmada nesta rodada.',
    ),
}
