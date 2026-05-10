"""Extract pipeline_state table from files.

Revision ID: 006
Revises: 005
Create Date: 2026-02-18

Changes:
- Create `pipeline_state` table with processing state columns
- Migrate data from `files` to `pipeline_state`
- Drop moved columns from `files` table
- Drop old composite index, add new index on pipeline_state

Related to issue #100: Decompose FileIndex god object
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create pipeline_state table
    op.create_table(
        "pipeline_state",
        sa.Column("file_id", sa.String(36), sa.ForeignKey("files.file_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("current_stage", sa.String(32), nullable=False, server_default="dispatcher"),
        sa.Column("overall_status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("embedded_chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=False, server_default=""),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_updated", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("chunking_strategy", sa.String(100), nullable=False, server_default=""),
        sa.Column("embedding_model", sa.String(100), nullable=False, server_default=""),
        sa.Column("vector_db_targets", sa.Text, nullable=False, server_default="[]"),
    )

    op.create_index(
        "ix_pipeline_state_status",
        "pipeline_state",
        ["overall_status", "current_stage"],
    )

    # 2. Migrate data from files to pipeline_state
    op.execute(
        """
        INSERT INTO pipeline_state (
            file_id, current_stage, overall_status, chunk_count, embedded_chunk_count,
            error_message, retry_count, last_updated, chunking_strategy, embedding_model,
            vector_db_targets
        )
        SELECT
            file_id, current_stage, overall_status, chunk_count, embedded_chunk_count,
            error_message, retry_count, last_updated, chunking_strategy, embedding_model,
            vector_db_targets
        FROM files
        """
    )

    # 3. Drop the old composite index that references columns being removed
    op.drop_index("ix_files_tenant_status", table_name="files")

    # 4. Drop moved columns from files table
    # SQL Server requires dropping default constraints before dropping columns
    for col_name in [
        "current_stage", "overall_status", "chunk_count", "embedded_chunk_count",
        "error_message", "retry_count", "chunking_strategy", "embedding_model",
        "vector_db_targets",
    ]:
        op.execute(
            f"""
            DECLARE @constraint_name NVARCHAR(256)
            SELECT @constraint_name = dc.name
            FROM sys.default_constraints dc
            INNER JOIN sys.columns c ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
            WHERE OBJECT_NAME(dc.parent_object_id) = 'files' AND c.name = '{col_name}'
            IF @constraint_name IS NOT NULL
                EXEC('ALTER TABLE files DROP CONSTRAINT ' + @constraint_name)
            """
        )
        op.drop_column("files", col_name)


def downgrade() -> None:
    # 1. Re-add columns to files table
    op.add_column("files", sa.Column("current_stage", sa.String(32), nullable=False, server_default="dispatcher"))
    op.add_column("files", sa.Column("overall_status", sa.String(32), nullable=False, server_default="queued"))
    op.add_column("files", sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"))
    op.add_column("files", sa.Column("embedded_chunk_count", sa.Integer, nullable=False, server_default="0"))
    op.add_column("files", sa.Column("error_message", sa.Text, nullable=False, server_default=""))
    op.add_column("files", sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"))
    op.add_column("files", sa.Column("chunking_strategy", sa.String(100), nullable=False, server_default=""))
    op.add_column("files", sa.Column("embedding_model", sa.String(100), nullable=False, server_default=""))
    op.add_column("files", sa.Column("vector_db_targets", sa.Text, nullable=False, server_default="[]"))

    # 2. Copy data back from pipeline_state to files
    op.execute(
        """
        UPDATE f
        SET f.current_stage = ps.current_stage,
            f.overall_status = ps.overall_status,
            f.chunk_count = ps.chunk_count,
            f.embedded_chunk_count = ps.embedded_chunk_count,
            f.error_message = ps.error_message,
            f.retry_count = ps.retry_count,
            f.chunking_strategy = ps.chunking_strategy,
            f.embedding_model = ps.embedding_model,
            f.vector_db_targets = ps.vector_db_targets
        FROM files f
        INNER JOIN pipeline_state ps ON f.file_id = ps.file_id
        """
    )

    # 3. Re-create the old composite index
    op.create_index(
        "ix_files_tenant_status",
        "files",
        ["tenant_id", "overall_status", "current_stage"],
    )

    # 4. Drop pipeline_state table
    op.drop_index("ix_pipeline_state_status", table_name="pipeline_state")
    op.drop_table("pipeline_state")
