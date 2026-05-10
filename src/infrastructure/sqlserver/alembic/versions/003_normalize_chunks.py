"""Normalize chunks storage by splitting processing metadata.

Revision ID: 003
Revises: 002
Create Date: 2026-02-13

Changes:
- Create `chunk_metadata` table for embedding status + flexible metadata JSON
- Remove redundant parent/status columns from `chunks`:
  - file_version
  - tenant_id
  - embedding_status
  - vector_db_ids
  - metadata_json
- Replace unique constraint `(file_id, file_version, chunk_index)` with
  `(file_id, chunk_index)`
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_default_constraints_for_chunks(columns: list[str]) -> None:
    """Drop SQL Server default constraints for the given chunks columns."""
    quoted = ", ".join(f"'{col}'" for col in columns)
    op.execute(
        f"""
        DECLARE @sql NVARCHAR(MAX) = N'';
        SELECT @sql = @sql + N'ALTER TABLE [chunks] DROP CONSTRAINT [' + dc.name + N'];'
        FROM sys.default_constraints dc
        INNER JOIN sys.columns c ON dc.parent_object_id = c.object_id
            AND dc.parent_column_id = c.column_id
        INNER JOIN sys.tables t ON t.object_id = c.object_id
        WHERE t.name = 'chunks'
          AND c.name IN ({quoted});
        IF LEN(@sql) > 0 EXEC sp_executesql @sql;
        """
    )


def upgrade() -> None:
    # 1) Create chunk_metadata table
    op.create_table(
        "chunk_metadata",
        sa.Column(
            "chunk_id",
            sa.String(200),
            sa.ForeignKey("chunks.chunk_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("embedding_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_chunk_metadata_status", "chunk_metadata", ["embedding_status"])

    # 2) Drop old indexes/constraints that depend on removed columns
    op.execute(
        """
        IF EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_chunks_file_status' AND object_id = OBJECT_ID('chunks')
        )
        DROP INDEX ix_chunks_file_status ON chunks
        """
    )
    op.execute(
        """
        IF EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_chunks_tenant_file' AND object_id = OBJECT_ID('chunks')
        )
        DROP INDEX ix_chunks_tenant_file ON chunks
        """
    )
    op.execute(
        """
        IF EXISTS (
            SELECT 1 FROM sys.key_constraints
            WHERE [name] = 'ux_chunks_file_version_index' AND [parent_object_id] = OBJECT_ID('chunks')
        )
        ALTER TABLE chunks DROP CONSTRAINT ux_chunks_file_version_index
        """
    )

    # 3) Drop default constraints, then legacy columns
    _drop_default_constraints_for_chunks(
        ["file_version", "tenant_id", "embedding_status", "vector_db_ids", "metadata_json"]
    )
    op.drop_column("chunks", "file_version")
    op.drop_column("chunks", "tenant_id")
    op.drop_column("chunks", "embedding_status")
    op.drop_column("chunks", "vector_db_ids")
    op.drop_column("chunks", "metadata_json")

    # 4) Add new uniqueness rule
    op.create_unique_constraint(
        "ux_chunks_file_index",
        "chunks",
        ["file_id", "chunk_index"],
    )


def downgrade() -> None:
    # 1) Restore legacy columns
    op.add_column("chunks", sa.Column("file_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("chunks", sa.Column("tenant_id", sa.String(length=64), nullable=False, server_default="default"))
    op.add_column(
        "chunks",
        sa.Column("embedding_status", sa.String(length=32), nullable=False, server_default="pending"),
    )
    op.add_column(
        "chunks",
        sa.Column("vector_db_ids", sa.Text(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "chunks",
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
    )

    # 2) Backfill embedding_status from chunk_metadata (best-effort)
    op.execute(
        """
        UPDATE c
        SET c.embedding_status = cm.embedding_status
        FROM chunks c
        INNER JOIN chunk_metadata cm ON cm.chunk_id = c.chunk_id
        """
    )

    # 3) Restore constraints/indexes
    op.drop_constraint("ux_chunks_file_index", "chunks", type_="unique")
    op.create_unique_constraint(
        "ux_chunks_file_version_index",
        "chunks",
        ["file_id", "file_version", "chunk_index"],
    )
    op.create_index(
        "ix_chunks_file_status",
        "chunks",
        ["file_id", "file_version", "embedding_status"],
    )
    op.create_index("ix_chunks_tenant_file", "chunks", ["tenant_id", "file_id"])

    # 4) Drop chunk_metadata table
    op.drop_index("ix_chunk_metadata_status", table_name="chunk_metadata")
    op.drop_table("chunk_metadata")
