"""baseline v35 — schema legado (tabelas antigas, sem tenant_id)

Representa exatamente o schema da v35: as 14 tabelas de domínio como
existiam antes da integração do BuyerRadar, SEM tenant_id.

Um banco v35 existente é "carimbado" nesta revision (via
`python cli.py prepare-v36-migration`, que valida o schema antes de
carimbar) SEM recriar nada. Um banco vazio roda esta revision de verdade.
O `if <tabela> not in existentes` garante que os dois caminhos funcionem
e que rodar duas vezes não quebre.

Revision ID: 605e28a0a5b4
Revises:
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa

revision = '605e28a0a5b4'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existentes = set(inspector.get_table_names())

    if 'bot_jobs' not in existentes:
        op.create_table(
            'bot_jobs',
            sa.Column('id', sa.Integer, primary_key=True, index=True, nullable=True),
            sa.Column('created_at', sa.DateTime, nullable=False),
            sa.Column('updated_at', sa.DateTime, nullable=False),
            sa.Column('input_original', sa.String(500), nullable=False),
            sa.Column('tipo_identificado', sa.String(50), nullable=False),
            sa.Column('objetivo', sa.String(30), nullable=False),
            sa.Column('status', sa.String(20), nullable=False),
            sa.Column('resumo_humano', sa.Text, nullable=True),
            sa.Column('proxima_acao', sa.Text, nullable=True),
            sa.Column('raw', sa.JSON, nullable=True),
        )
    if 'bot_steps' not in existentes:
        op.create_table(
            'bot_steps',
            sa.Column('id', sa.Integer, primary_key=True, index=True, nullable=True),
            sa.Column('job_id', sa.Integer, index=True, nullable=False),
            sa.Column('bot_name', sa.String(50), nullable=False),
            sa.Column('status', sa.String(20), nullable=False),
            sa.Column('started_at', sa.DateTime, nullable=False),
            sa.Column('finished_at', sa.DateTime, nullable=True),
            sa.Column('resultado', sa.JSON, nullable=True),
            sa.Column('warning', sa.Text, nullable=True),
            sa.Column('erro', sa.Text, nullable=True),
            sa.Column('evidence_id', sa.Integer, nullable=True),
            sa.Column('next_action', sa.Text, nullable=True),
        )
    if 'certificate_records' not in existentes:
        op.create_table(
            'certificate_records',
            sa.Column('id', sa.Integer, primary_key=True, index=True, nullable=True),
            sa.Column('created_at', sa.DateTime, nullable=False),
            sa.Column('source_id', sa.String(80), index=True, nullable=False),
            sa.Column('certificate_type', sa.String(50), nullable=False),
            sa.Column('document_masked', sa.String(50), nullable=True),
            sa.Column('name_consulted', sa.String(255), nullable=True),
            sa.Column('status', sa.String(60), nullable=False),
            sa.Column('message', sa.Text, nullable=True),
            sa.Column('validation_code', sa.String(255), nullable=True),
            sa.Column('pdf_path', sa.String(500), nullable=True),
            sa.Column('fonte_url', sa.String(500), nullable=True),
            sa.Column('issued_at', sa.String(50), nullable=True),
            sa.Column('valid_until', sa.String(50), nullable=True),
            sa.Column('raw', sa.JSON, nullable=True),
        )
    if 'diligencia_logs' not in existentes:
        op.create_table(
            'diligencia_logs',
            sa.Column('id', sa.Integer, primary_key=True, index=True, nullable=True),
            sa.Column('created_at', sa.DateTime, nullable=False),
            sa.Column('input_original', sa.String(500), nullable=False),
            sa.Column('tipo_identificado', sa.String(50), nullable=False),
            sa.Column('valor_normalizado', sa.String(500), nullable=False),
            sa.Column('objetivo', sa.String(30), nullable=False),
            sa.Column('status', sa.String(30), nullable=False),
            sa.Column('resumo_humano', sa.Text, nullable=True),
            sa.Column('proxima_acao_recomendada', sa.Text, nullable=True),
            sa.Column('resultados_confirmados', sa.JSON, nullable=True),
            sa.Column('indicios', sa.JSON, nullable=True),
            sa.Column('pendencias', sa.JSON, nullable=True),
            sa.Column('fontes_manuais_recomendadas', sa.JSON, nullable=True),
            sa.Column('raw_avancado', sa.JSON, nullable=True),
        )
    if 'intake_cases' not in existentes:
        op.create_table(
            'intake_cases',
            sa.Column('id', sa.Integer, primary_key=True, index=True, nullable=True),
            sa.Column('created_at', sa.DateTime, nullable=False),
            sa.Column('lead_id', sa.Integer, index=True, nullable=False),
            sa.Column('input_original', sa.Text, nullable=False),
            sa.Column('dados_extraidos', sa.JSON, nullable=True),
            sa.Column('processos_detectados', sa.JSON, nullable=True),
            sa.Column('divergencias', sa.JSON, nullable=True),
            sa.Column('dados_faltantes', sa.JSON, nullable=True),
            sa.Column('resposta_sugerida', sa.Text, nullable=True),
            sa.Column('job_id', sa.Integer, nullable=True),
            sa.Column('job_id_referencia', sa.Integer, nullable=True),
            sa.Column('status', sa.String(20), nullable=False),
        )
    if 'leads' not in existentes:
        op.create_table(
            'leads',
            sa.Column('id', sa.Integer, primary_key=True, index=True, nullable=True),
            sa.Column('created_at', sa.DateTime, nullable=False),
            sa.Column('telefone', sa.String(30), nullable=True),
            sa.Column('nome', sa.String(255), nullable=True),
            sa.Column('cpf', sa.String(20), nullable=True),
            sa.Column('cnpj', sa.String(20), nullable=True),
            sa.Column('origem', sa.String(30), nullable=False),
            sa.Column('status', sa.String(20), nullable=False),
        )
    if 'manual_evidences' not in existentes:
        op.create_table(
            'manual_evidences',
            sa.Column('id', sa.Integer, primary_key=True, index=True, nullable=True),
            sa.Column('created_at', sa.DateTime, nullable=False),
            sa.Column('fonte', sa.String(255), nullable=False),
            sa.Column('referencia', sa.String(255), nullable=True),
            sa.Column('texto', sa.Text, nullable=True),
            sa.Column('arquivo_nome', sa.String(255), nullable=True),
            sa.Column('arquivo_caminho', sa.String(500), nullable=True),
        )
    if 'opportunity_leads' not in existentes:
        op.create_table(
            'opportunity_leads',
            sa.Column('id', sa.Integer, primary_key=True, index=True, nullable=True),
            sa.Column('created_at', sa.DateTime, nullable=False),
            sa.Column('dedupe_key', sa.String(200), index=True, nullable=True),
            sa.Column('first_seen_at', sa.DateTime, nullable=True),
            sa.Column('last_seen_at', sa.DateTime, nullable=True),
            sa.Column('seen_count', sa.Integer, nullable=False),
            sa.Column('source', sa.String(50), nullable=False),
            sa.Column('process_number', sa.String(40), nullable=True),
            sa.Column('normalized_cnj', sa.String(20), nullable=True),
            sa.Column('tribunal', sa.String(20), nullable=True),
            sa.Column('segment', sa.String(50), nullable=True),
            sa.Column('uf', sa.String(5), nullable=True),
            sa.Column('debtor', sa.String(255), nullable=True),
            sa.Column('creditor_name', sa.String(255), nullable=True),
            sa.Column('creditor_document_masked', sa.String(20), nullable=True),
            sa.Column('creditor_document_hash', sa.String(64), index=True, nullable=True),
            sa.Column('lawyer_name', sa.String(255), nullable=True),
            sa.Column('signal_type', sa.String(30), nullable=True),
            sa.Column('phase', sa.String(50), nullable=True),
            sa.Column('estimated_opportunity_type', sa.String(50), nullable=True),
            sa.Column('confidence_score', sa.Integer, nullable=False),
            sa.Column('priority', sa.String(10), nullable=False),
            sa.Column('status', sa.String(20), nullable=False),
            sa.Column('bot_job_id', sa.Integer, nullable=True),
            sa.Column('dossie_url', sa.String(200), nullable=True),
            sa.Column('next_action', sa.Text, nullable=True),
            sa.Column('publication_text', sa.Text, nullable=True),
            sa.Column('matched_terms', sa.JSON, nullable=True),
        )
    if 'process_results' not in existentes:
        op.create_table(
            'process_results',
            sa.Column('id', sa.Integer, primary_key=True, index=True, nullable=True),
            sa.Column('search_log_id', sa.Integer, index=True, nullable=False),
            sa.Column('created_at', sa.DateTime, nullable=False),
            sa.Column('provider', sa.String(50), nullable=False),
            sa.Column('tribunal', sa.String(50), nullable=True),
            sa.Column('numero_processo', sa.String(50), index=True, nullable=True),
            sa.Column('classe', sa.String(255), nullable=True),
            sa.Column('assunto', sa.Text, nullable=True),
            sa.Column('orgao_julgador', sa.Text, nullable=True),
            sa.Column('data_ajuizamento', sa.String(50), nullable=True),
            sa.Column('ultima_atualizacao', sa.String(50), nullable=True),
            sa.Column('precatorio_score', sa.Integer, nullable=False),
            sa.Column('precatorio_flags', sa.JSON, nullable=True),
            sa.Column('raw', sa.JSON, nullable=True),
        )
    if 'publication_hits' not in existentes:
        op.create_table(
            'publication_hits',
            sa.Column('id', sa.Integer, primary_key=True, index=True, nullable=True),
            sa.Column('watcher_run_id', sa.Integer, index=True, nullable=False),
            sa.Column('source', sa.String(50), nullable=False),
            sa.Column('tribunal', sa.String(20), nullable=True),
            sa.Column('publication_date', sa.String(20), nullable=True),
            sa.Column('process_number', sa.String(40), nullable=True),
            sa.Column('normalized_cnj', sa.String(20), nullable=True),
            sa.Column('parties_text', sa.Text, nullable=True),
            sa.Column('lawyers_text', sa.Text, nullable=True),
            sa.Column('publication_text', sa.Text, nullable=True),
            sa.Column('text_hash', sa.String(64), index=True, nullable=True),
            sa.Column('matched_terms', sa.JSON, nullable=True),
            sa.Column('signal_type', sa.String(30), nullable=True),
            sa.Column('confidence', sa.String(10), nullable=True),
            sa.Column('source_url', sa.String(500), nullable=True),
            sa.Column('raw', sa.JSON, nullable=True),
        )
    if 'search_logs' not in existentes:
        op.create_table(
            'search_logs',
            sa.Column('id', sa.Integer, primary_key=True, index=True, nullable=True),
            sa.Column('created_at', sa.DateTime, nullable=False),
            sa.Column('provider', sa.String(50), nullable=False),
            sa.Column('search_type', sa.String(50), nullable=False),
            sa.Column('search_key_masked', sa.String(255), nullable=False),
            sa.Column('tribunals', sa.Text, nullable=False),
            sa.Column('status', sa.String(50), nullable=False),
            sa.Column('raw_request', sa.JSON, nullable=True),
            sa.Column('notes', sa.Text, nullable=True),
        )
    if 'stj_official_files' not in existentes:
        op.create_table(
            'stj_official_files',
            sa.Column('id', sa.Integer, primary_key=True, index=True, nullable=True),
            sa.Column('year', sa.Integer, nullable=True),
            sa.Column('natureza', sa.String(50), nullable=True),
            sa.Column('entidade_devedora', sa.String(255), nullable=True),
            sa.Column('source_url', sa.String(1000), nullable=False),
            sa.Column('local_path', sa.String(500), nullable=True),
            sa.Column('original_filename', sa.String(255), nullable=True),
            sa.Column('downloaded_at', sa.DateTime, nullable=True),
            sa.Column('file_hash', sa.String(64), nullable=True),
            sa.Column('row_count', sa.Integer, nullable=True),
            sa.Column('status', sa.String(20), nullable=False),
            sa.Column('error', sa.Text, nullable=True),
        )
    if 'watcher_runs' not in existentes:
        op.create_table(
            'watcher_runs',
            sa.Column('id', sa.Integer, primary_key=True, index=True, nullable=True),
            sa.Column('watcher_name', sa.String(50), nullable=False),
            sa.Column('started_at', sa.DateTime, nullable=False),
            sa.Column('finished_at', sa.DateTime, nullable=True),
            sa.Column('status', sa.String(20), nullable=False),
            sa.Column('date_from', sa.String(20), nullable=True),
            sa.Column('date_to', sa.String(20), nullable=True),
            sa.Column('tribunals_scanned', sa.JSON, nullable=True),
            sa.Column('total_publications', sa.Integer, nullable=False),
            sa.Column('total_matches', sa.Integer, nullable=False),
            sa.Column('total_leads_created', sa.Integer, nullable=False),
            sa.Column('error', sa.Text, nullable=True),
        )
    if 'whatsapp_messages' not in existentes:
        op.create_table(
            'whatsapp_messages',
            sa.Column('id', sa.Integer, primary_key=True, index=True, nullable=True),
            sa.Column('lead_id', sa.Integer, index=True, nullable=False),
            sa.Column('telefone', sa.String(30), nullable=True),
            sa.Column('texto_original', sa.Text, nullable=True),
            sa.Column('arquivo_evidencia', sa.String(500), nullable=True),
            sa.Column('received_at', sa.DateTime, nullable=False),
            sa.Column('raw', sa.JSON, nullable=True),
        )

def downgrade() -> None:
    for tabela in [
        'opportunity_leads', 'publication_hits', 'watcher_runs', 'intake_cases',
        'whatsapp_messages', 'leads', 'stj_official_files', 'bot_steps', 'bot_jobs',
        'diligencia_logs', 'manual_evidences', 'certificate_records', 'process_results',
        'search_logs',
    ]:
        op.execute(f'DROP TABLE IF EXISTS {tabela}')
