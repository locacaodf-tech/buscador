from datetime import datetime
from sqlalchemy import DateTime, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class SearchLog(Base):
    __tablename__ = 'search_logs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
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
