"""Metadata refactoring: promote document_type/language, drop duplicate metadata_json.

Revision ID: 005
Revises: 004
Create Date: 2026-02-17

Changes:
- Add document_type and language columns to file_metadata table
- Backfill from files.metadata_json
- Drop duplicate metadata_json from file_metadata table
- Add index on document_type for type-based filtering

Related to issue #98: Incremental metadata refactoring
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new promoted columns
    op.add_column(
        "file_metadata",
        sa.Column("document_type", sa.String(100), nullable=True),
    )
    op.add_column(
        "file_metadata",
        sa.Column("language", sa.String(10), nullable=True, server_default="en"),
    )

    # Backfill from files.metadata_json using SQL Server JSON_VALUE
    op.execute(
        """
        UPDATE fm
        SET fm.document_type = JSON_VALUE(f.metadata_json, '$.document_type'),
            fm.language = COALESCE(JSON_VALUE(f.metadata_json, '$.language'), 'en')
        FROM file_metadata fm
        INNER JOIN files f ON fm.file_id = f.file_id
        """
    )

    # Drop default constraint on metadata_json before dropping column (SQL Server requirement)
    op.execute(
        """
        DECLARE @constraint_name NVARCHAR(256)
        SELECT @constraint_name = dc.name
        FROM sys.default_constraints dc
        INNER JOIN sys.columns c ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
        WHERE OBJECT_NAME(dc.parent_object_id) = 'file_metadata' AND c.name = 'metadata_json'
        IF @constraint_name IS NOT NULL
            EXEC('ALTER TABLE file_metadata DROP CONSTRAINT ' + @constraint_name)
        """
    )

    # Drop duplicate metadata_json column from file_metadata
    op.drop_column("file_metadata", "metadata_json")

    # Add index on document_type
    op.create_index(
        "ix_metadata_document_type",
        "file_metadata",
        ["document_type"],
    )


def downgrade() -> None:
    # Drop the index
    op.drop_index("ix_metadata_document_type", table_name="file_metadata")

    # Re-add metadata_json column
    op.add_column(
        "file_metadata",
        sa.Column("metadata_json", sa.Text, nullable=False, server_default="{}"),
    )

    # Backfill metadata_json from files table
    op.execute(
        """
        UPDATE fm
        SET fm.metadata_json = f.metadata_json
        FROM file_metadata fm
        INNER JOIN files f ON fm.file_id = f.file_id
        """
    )

    # Drop new columns
    op.drop_column("file_metadata", "language")
    op.drop_column("file_metadata", "document_type")
