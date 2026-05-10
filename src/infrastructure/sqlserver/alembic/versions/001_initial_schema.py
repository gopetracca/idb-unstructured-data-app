"""Initial SQL Server schema with temporal tables.

Revision ID: 001
Revises: None
Create Date: 2026-02-07

Creates the following tables:
- files (with system versioning / temporal table)
- file_metadata
- chunks
- chunk_vector_refs
- processing_events
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==========================================
    # 1. files table (with temporal support)
    # ==========================================
    # Create base table first via SQLAlchemy, then add temporal columns via raw SQL
    op.create_table(
        "files",
        sa.Column("file_id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("ezshare_id", sa.String(100), nullable=True),
        sa.Column("blob_name", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False, server_default="application/octet-stream"),
        sa.Column("size_bytes", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("content_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("file_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("current_stage", sa.String(32), nullable=False, server_default="dispatcher"),
        sa.Column("overall_status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("collection_name", sa.String(100), nullable=True),
        sa.Column("chunking_strategy", sa.String(100), nullable=False, server_default=""),
        sa.Column("embedding_model", sa.String(100), nullable=False, server_default=""),
        sa.Column("vector_db_targets", sa.Text, nullable=False, server_default="[]"),
        sa.Column("metadata_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("embedded_chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=False, server_default=""),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("upload_timestamp", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("last_updated", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.String(100), nullable=True),
        sa.Column("updated_by", sa.String(100), nullable=True),
    )

    # Indexes for files
    op.create_index(
        "ix_files_tenant_status",
        "files",
        ["tenant_id", "overall_status", "current_stage"],
    )
    op.create_index(
        "ix_files_content_hash",
        "files",
        ["content_hash"],
    )

    # Filtered unique constraint for tenant + ezshare_id (only where ezshare_id IS NOT NULL)
    # SQLAlchemy doesn't support filtered unique constraints natively, use raw SQL
    op.execute(
        """
        CREATE UNIQUE INDEX ux_files_tenant_ezshare
        ON files(tenant_id, ezshare_id)
        WHERE ezshare_id IS NOT NULL
        """
    )

    # Add temporal table support (SQL Server specific)
    # Add system-time period columns
    op.execute(
        """
        ALTER TABLE files ADD
            SysStartTime DATETIME2 GENERATED ALWAYS AS ROW START
                CONSTRAINT DF_files_SysStart DEFAULT SYSUTCDATETIME(),
            SysEndTime DATETIME2 GENERATED ALWAYS AS ROW END
                CONSTRAINT DF_files_SysEnd DEFAULT CONVERT(DATETIME2, '9999-12-31 23:59:59.9999999'),
            PERIOD FOR SYSTEM_TIME (SysStartTime, SysEndTime)
        """
    )

    # Enable system versioning
    op.execute(
        """
        ALTER TABLE files SET (SYSTEM_VERSIONING = ON (HISTORY_TABLE = dbo.files_history))
        """
    )

    # ==========================================
    # 2. file_metadata table
    # ==========================================
    op.create_table(
        "file_metadata",
        sa.Column("file_id", sa.String(36), sa.ForeignKey("files.file_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("metadata_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("sector", sa.String(100), nullable=True),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("operation_number", sa.String(50), nullable=True),
        sa.Column("operation_type", sa.String(100), nullable=True),
        sa.Column("dept_id", sa.String(100), nullable=True),
        sa.Column("document_author", sa.String(200), nullable=True),
        sa.Column("document_name", sa.String(500), nullable=True),
        sa.Column("document_url", sa.Text, nullable=True),
        sa.Column("file_extension", sa.String(10), nullable=True),
        sa.Column("disclosed", sa.Boolean, nullable=True),
        sa.Column("access_to_information_policy", sa.String(50), nullable=True),
        sa.Column("document_publish_date", sa.DateTime, nullable=True),
        sa.Column("document_created_date", sa.DateTime, nullable=True),
        sa.Column("document_approval_date", sa.DateTime, nullable=True),
    )

    op.create_index("ix_metadata_country_sector_year", "file_metadata", ["country", "sector", "year"])
    op.create_index("ix_metadata_operation_number", "file_metadata", ["operation_number"])
    op.create_index("ix_metadata_dept_id", "file_metadata", ["dept_id"])
    op.create_index("ix_metadata_document_author", "file_metadata", ["document_author"])

    # ==========================================
    # 3. chunks table
    # ==========================================
    op.create_table(
        "chunks",
        sa.Column("chunk_id", sa.String(200), primary_key=True),
        sa.Column("file_id", sa.String(36), sa.ForeignKey("files.file_id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("text_preview", sa.String(500), nullable=True),
        sa.Column("start_char", sa.Integer, nullable=False, server_default="0"),
        sa.Column("end_char", sa.Integer, nullable=False, server_default="0"),
        sa.Column("page_number", sa.Integer, nullable=True),
        sa.Column("embedding_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("vector_db_ids", sa.Text, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("file_id", "file_version", "chunk_index", name="ux_chunks_file_version_index"),
    )

    op.create_index("ix_chunks_file_status", "chunks", ["file_id", "file_version", "embedding_status"])
    op.create_index("ix_chunks_tenant_file", "chunks", ["tenant_id", "file_id"])

    # ==========================================
    # 4. chunk_vector_refs table
    # ==========================================
    op.create_table(
        "chunk_vector_refs",
        sa.Column("chunk_id", sa.String(200), sa.ForeignKey("chunks.chunk_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("db_name", sa.String(64), primary_key=True),
        sa.Column("vector_doc_id", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_vector_refs_db_doc", "chunk_vector_refs", ["db_name", "vector_doc_id"])

    # ==========================================
    # 5. processing_events table
    # ==========================================
    op.create_table(
        "processing_events",
        sa.Column("event_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("file_id", sa.String(36), sa.ForeignKey("files.file_id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("from_stage", sa.String(32), nullable=True),
        sa.Column("to_stage", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("event_timestamp", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("duration_ms", sa.BigInteger, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("metadata_json", sa.Text, nullable=True),
    )

    op.create_index("ix_events_file_timestamp", "processing_events", ["file_id", sa.text("event_timestamp DESC")])
    op.create_index("ix_events_tenant_stage", "processing_events", ["tenant_id", "to_stage", sa.text("event_timestamp DESC")])


def downgrade() -> None:
    # Disable temporal table before dropping
    op.execute("ALTER TABLE files SET (SYSTEM_VERSIONING = OFF)")
    op.execute("DROP TABLE IF EXISTS dbo.files_history")

    op.drop_table("processing_events")
    op.drop_table("chunk_vector_refs")
    op.drop_table("chunks")
    op.drop_table("file_metadata")
    op.drop_table("files")
