from datetime import datetime, timezone
from sqlalchemy import DateTime, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class SearchLog(Base):
    __tablename__ = 'search_logs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    search_type: Mapped[str] = mapped_column(String(50), nullable=False)
    search_key_masked: Mapped[str] = mapped_column(String(255), nullable=False)
    tribunals: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(50), default='created')
    raw_request: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProcessResult(Base):
    __tablename__ = 'process_results'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    search_log_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    tribunal: Mapped[str | None] = mapped_column(String(50), nullable=True)
    numero_processo: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    classe: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assunto: Mapped[str | None] = mapped_column(Text, nullable=True)
    orgao_julgador: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_ajuizamento: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ultima_atualizacao: Mapped[str | None] = mapped_column(String(50), nullable=True)
    precatorio_score: Mapped[int] = mapped_column(Integer, default=0)
    precatorio_flags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class CertificateRecord(Base):
    """Pedido/resultado de emissão de certidão (certificate_center).

    Regra inegociável: status 'negativa' ou 'positiva' só podem existir se
    houver documento/código de validação real da fonte oficial. Sem isso, o
    status honesto é 'pendente', 'erro', 'requer_*' ou 'nao_integrado'.
    """

    __tablename__ = 'certificate_records'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    source_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    certificate_type: Mapped[str] = mapped_column(String(50), nullable=False)  # civel, criminal, fiscal_cnd, eleitoral...
    document_masked: Mapped[str | None] = mapped_column(String(50), nullable=True)
    name_consulted: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(60), nullable=False, default='pendente')
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    fonte_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    issued_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    valid_until: Mapped[str | None] = mapped_column(String(50), nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ManualEvidence(Base):
    """Registro manual de evidência — pra quando uma fonte ainda não é
    automatizada, mas o usuário já conseguiu a informação manualmente
    (copiou texto do portal, anexou PDF/print/XLSX) e quer guardar isso
    junto do resto do dossiê. Não inventa dado nenhum: é só um cofre pro
    que o próprio usuário coletou e confirma que é real."""

    __tablename__ = 'manual_evidences'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    fonte: Mapped[str] = mapped_column(String(255), nullable=False)  # nome da fonte/tribunal/site consultado manualmente
    referencia: Mapped[str | None] = mapped_column(String(255), nullable=True)  # CNJ/CPF/precatório relacionado, se houver
    texto: Mapped[str | None] = mapped_column(Text, nullable=True)  # texto colado pelo usuário
    arquivo_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    arquivo_caminho: Mapped[str | None] = mapped_column(String(500), nullable=True)


class DiligenciaLog(Base):
    """Cada chamada ao Motor Operacional de Diligência (POST /api/diligencia)
    fica salva aqui — pra poder reabrir depois e virar dossiê, sem precisar
    rodar tudo de novo. Guarda o resultado completo (JSON), não só um
    resumo, porque o dossiê precisa de todo o detalhe."""

    __tablename__ = 'diligencia_logs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    input_original: Mapped[str] = mapped_column(String(500), nullable=False)
    tipo_identificado: Mapped[str] = mapped_column(String(50), nullable=False)
    valor_normalizado: Mapped[str] = mapped_column(String(500), nullable=False)
    objetivo: Mapped[str] = mapped_column(String(30), nullable=False, default='completo')
    status: Mapped[str] = mapped_column(String(30), nullable=False, default='completed')
    resumo_humano: Mapped[str | None] = mapped_column(Text, nullable=True)
    proxima_acao_recomendada: Mapped[str | None] = mapped_column(Text, nullable=True)
    resultados_confirmados: Mapped[list | None] = mapped_column(JSON, nullable=True)
    indicios: Mapped[list | None] = mapped_column(JSON, nullable=True)
    pendencias: Mapped[list | None] = mapped_column(JSON, nullable=True)
    fontes_manuais_recomendadas: Mapped[list | None] = mapped_column(JSON, nullable=True)
    raw_avancado: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class BotJob(Base):
    """Um job de execução dos bots (v30) — snapshot completo de uma
    diligência processada pela camada de bots, com visibilidade de cada
    etapa (ver BotStep). Não é uma fila assíncrona com workers separados
    (este é um FastAPI síncrono) — é execução dentro da própria requisição,
    registrada aqui pra dar rastreabilidade e permitir retomar quando um
    bot específico (o PortalBot) pausa esperando intervenção humana."""

    __tablename__ = 'bot_jobs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    input_original: Mapped[str] = mapped_column(String(500), nullable=False)
    tipo_identificado: Mapped[str] = mapped_column(String(50), nullable=False)
    objetivo: Mapped[str] = mapped_column(String(30), nullable=False, default='completo')
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='pending')  # pending|running|partial|completed|failed|waiting_user
    resumo_humano: Mapped[str | None] = mapped_column(Text, nullable=True)
    proxima_acao: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class BotStep(Base):
    """Uma etapa (um bot específico) dentro de um BotJob."""

    __tablename__ = 'bot_steps'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    bot_name: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resultado: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    erro: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)


class StjOfficialFile(Base):
    """Arquivo oficial do STJ baixado automaticamente pelo StjBot (v30.2) —
    diferente do upload manual (que fica em data/stj_uploads sem registro
    próprio), este modelo rastreia origem, quando foi baixado e o
    resultado do download, pra nunca fingir que uma tentativa deu certo."""

    __tablename__ = 'stj_official_files'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    natureza: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entidade_devedora: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    local_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='pending')  # pending|downloaded|failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
