"""Add publication-specific columns to file_metadata table.

Revision ID: 008
Revises: 007
Create Date: 2026-04-02

Changes:
- Add `journal`, `doi`, `issn`, `peer_reviewed`, `publication_type`, `publication_date`
  columns to `file_metadata` table for research publications
- Add indexes for efficient publication filtering

Related to issue #111: Extensible metadata architecture for multi-document types
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add publication-specific columns to file_metadata
    op.add_column(
        "file_metadata",
        sa.Column("journal", sa.String(500), nullable=True),
    )
    op.add_column(
        "file_metadata",
        sa.Column("doi", sa.String(200), nullable=True),
    )
    op.add_column(
        "file_metadata",
        sa.Column("issn", sa.String(50), nullable=True),
    )
    op.add_column(
        "file_metadata",
        sa.Column("peer_reviewed", sa.Boolean, nullable=True),
    )
    op.add_column(
        "file_metadata",
        sa.Column("publication_type", sa.String(100), nullable=True),
    )
    op.add_column(
        "file_metadata",
        sa.Column("publication_date", sa.DateTime, nullable=True),
    )

    # Add indexes for publication filtering
    op.create_index("ix_metadata_doi", "file_metadata", ["doi"])
    op.create_index("ix_metadata_journal", "file_metadata", ["journal"])
    op.create_index("ix_metadata_peer_reviewed", "file_metadata", ["peer_reviewed"])


def downgrade() -> None:
    # Drop indexes first
    op.drop_index("ix_metadata_peer_reviewed", table_name="file_metadata")
    op.drop_index("ix_metadata_journal", table_name="file_metadata")
    op.drop_index("ix_metadata_doi", table_name="file_metadata")

    # Drop publication columns
    op.drop_column("file_metadata", "publication_date")
    op.drop_column("file_metadata", "publication_type")
    op.drop_column("file_metadata", "peer_reviewed")
    op.drop_column("file_metadata", "issn")
    op.drop_column("file_metadata", "doi")
    op.drop_column("file_metadata", "journal")
