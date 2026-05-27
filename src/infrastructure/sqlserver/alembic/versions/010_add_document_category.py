"""Add document_category column to file_metadata.

Revision ID: 010
Revises: 009
Create Date: 2026-05-26

Changes:
- Add `document_category` column (String 100, nullable) to file_metadata
- Copy current `document_type` values into `document_category` (they hold
  the schema-discriminator value: "operational" or "publication")
- Add index ix_metadata_document_category on document_category

The `document_type` column is NOT changed here — its values will be updated
separately (either via a backfill script or through normal document updates).
After migration:
  - document_category = "operational" | "publication"  (schema discriminator)
  - document_type     = NULL | user-defined value        (e.g. "PCR", "Report")
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add document_category column
    op.add_column(
        "file_metadata",
        sa.Column("document_category", sa.String(100), nullable=True),
    )

    # 2. Copy current document_type values into document_category
    #    (before this migration, document_type held "operational" / "publication")
    op.execute("UPDATE file_metadata SET document_category = document_type")

    # 3. Add index on document_category for efficient filtering
    op.create_index(
        "ix_metadata_document_category",
        "file_metadata",
        ["document_category"],
    )


def downgrade() -> None:
    op.drop_index("ix_metadata_document_category", table_name="file_metadata")
    op.drop_column("file_metadata", "document_category")
