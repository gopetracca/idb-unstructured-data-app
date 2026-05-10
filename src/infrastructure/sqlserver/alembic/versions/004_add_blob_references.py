"""Add blob reference columns for SSOT metadata consolidation.

Revision ID: 004
Revises: 003
Create Date: 2026-02-16

This migration adds explicit blob storage reference columns to the files
and chunks tables, establishing SQL Server as the single source of truth
for all metadata including blob storage locations.

Changes:
- Add raw_blob_ref and text_blob_ref to files table
- Add chunk_blob_ref and embedding_blob_ref to chunks table
- Populate existing records using conventional path patterns
- Add indexes for blob reference lookups

Related to issue #92: Consolidate metadata into SQL Server as SSOT
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add blob reference columns to files and chunks tables.

    Strategy:
    1. Add columns as nullable
    2. Populate from existing conventional paths
    3. Eventually can make NOT NULL after validation period
    """

    # ==========================================
    # 1. Add blob reference columns to files table
    # ==========================================

    # Disable system versioning temporarily to add columns
    # (required for temporal tables in SQL Server)
    op.execute(
        """
        ALTER TABLE files SET (SYSTEM_VERSIONING = OFF)
        """
    )

    # Add raw_blob_ref column (stores path to raw uploaded file)
    op.add_column(
        "files",
        sa.Column(
            "raw_blob_ref",
            sa.String(1024),
            nullable=True,
            comment="Blob storage path for raw uploaded file (e.g., tenant_id/file_id/filename)",
        ),
    )

    # Add text_blob_ref column (stores path to extracted text/markdown)
    op.add_column(
        "files",
        sa.Column(
            "text_blob_ref",
            sa.String(1024),
            nullable=True,
            comment="Blob storage path for extracted text (e.g., tenant_id/file_id/text.json)",
        ),
    )

    # Populate raw_blob_ref for existing files using conventional pattern
    # Pattern: {tenant_id}/{file_id}/{blob_name}
    op.execute(
        """
        UPDATE files
        SET raw_blob_ref = tenant_id + '/' + file_id + '/' + blob_name
        WHERE raw_blob_ref IS NULL
        """
    )

    # Populate text_blob_ref for files that have been processed (convert stage completed)
    # Pattern: {tenant_id}/{file_id}/text.json
    op.execute(
        """
        UPDATE files
        SET text_blob_ref = tenant_id + '/' + file_id + '/text.json'
        WHERE text_blob_ref IS NULL
          AND current_stage IN ('chunk', 'vectorize', 'ingest', 'completed')
        """
    )

    # Add same columns to history table (must match main table types: VARCHAR not NVARCHAR)
    op.execute(
        """
        ALTER TABLE files_history
        ADD raw_blob_ref VARCHAR(1024) NULL,
            text_blob_ref VARCHAR(1024) NULL
        """
    )

    # Re-enable system versioning
    op.execute(
        """
        ALTER TABLE files SET (SYSTEM_VERSIONING = ON (HISTORY_TABLE = dbo.files_history))
        """
    )

    # Add index for blob reference lookups (useful for validation queries)
    op.create_index(
        "ix_files_raw_blob_ref",
        "files",
        ["raw_blob_ref"],
    )

    op.create_index(
        "ix_files_text_blob_ref",
        "files",
        ["text_blob_ref"],
    )

    # ==========================================
    # 2. Add blob reference columns to chunks table
    # ==========================================

    # Add chunk_blob_ref column (stores path to chunk content)
    op.add_column(
        "chunks",
        sa.Column(
            "chunk_blob_ref",
            sa.String(1024),
            nullable=True,
            comment="Blob storage path for chunk content (e.g., tenant_id/file_id/chunks/chunk_id.json)",
        ),
    )

    # Add embedding_blob_ref column (stores path to embedding vectors if in blob storage)
    op.add_column(
        "chunks",
        sa.Column(
            "embedding_blob_ref",
            sa.String(1024),
            nullable=True,
            comment="Blob storage path for embedding vectors (if stored in blob storage)",
        ),
    )

    # Populate chunk_blob_ref for existing chunks using conventional pattern
    # Pattern: {tenant_id}/{file_id}/chunks/{chunk_id}.json
    # Need to get tenant_id from parent file via JOIN
    op.execute(
        """
        UPDATE c
        SET c.chunk_blob_ref = f.tenant_id + '/' + c.file_id + '/chunks/' + c.chunk_id + '.json'
        FROM chunks c
        INNER JOIN files f ON c.file_id = f.file_id
        WHERE c.chunk_blob_ref IS NULL
        """
    )

    # Add index for chunk blob reference lookups
    op.create_index(
        "ix_chunks_chunk_blob_ref",
        "chunks",
        ["chunk_blob_ref"],
    )

    op.create_index(
        "ix_chunks_embedding_blob_ref",
        "chunks",
        ["embedding_blob_ref"],
    )


def downgrade() -> None:
    """
    Remove blob reference columns from files and chunks tables.
    """

    # ==========================================
    # 1. Remove blob reference columns from chunks table
    # ==========================================

    op.drop_index("ix_chunks_embedding_blob_ref", "chunks")
    op.drop_index("ix_chunks_chunk_blob_ref", "chunks")

    op.drop_column("chunks", "embedding_blob_ref")
    op.drop_column("chunks", "chunk_blob_ref")

    # ==========================================
    # 2. Remove blob reference columns from files table
    # ==========================================

    op.drop_index("ix_files_text_blob_ref", "files")
    op.drop_index("ix_files_raw_blob_ref", "files")

    # Disable system versioning temporarily
    op.execute(
        """
        ALTER TABLE files SET (SYSTEM_VERSIONING = OFF)
        """
    )

    # Remove columns from main table
    op.drop_column("files", "text_blob_ref")
    op.drop_column("files", "raw_blob_ref")

    # Remove columns from history table
    op.execute(
        """
        ALTER TABLE files_history
        DROP COLUMN raw_blob_ref, text_blob_ref
        """
    )

    # Re-enable system versioning
    op.execute(
        """
        ALTER TABLE files SET (SYSTEM_VERSIONING = ON (HISTORY_TABLE = dbo.files_history))
        """
    )
