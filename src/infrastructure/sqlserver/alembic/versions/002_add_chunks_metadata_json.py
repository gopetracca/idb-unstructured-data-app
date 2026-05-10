"""Add metadata_json column to chunks table.

Revision ID: 002
Revises: 001
Create Date: 2026-02-11

Stores chunk metadata (chunking_strategy, section_path, has_table,
table_id, etc.) as a JSON text column, following the same pattern
used by the files and file_metadata tables.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column("metadata_json", sa.Text, nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("chunks", "metadata_json")
