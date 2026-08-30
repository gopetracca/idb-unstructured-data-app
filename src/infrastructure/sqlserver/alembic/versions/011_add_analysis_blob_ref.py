"""Add analysis_blob_ref to files for the verbatim extraction response.

Revision ID: 011
Revises: 010
Create Date: 2026-08-30

The `convert` stage now stores the Document Intelligence response verbatim as
`{tenant_id}/{file_id}/analysis.json` beside the extracted text. Blob references in SQL
are the source of truth for content location, so that path gets a column rather than
being reconstructed by convention.

The column is nullable and is NOT backfilled. Every row predating this migration was
extracted before the raw response was kept, so there is no blob at the conventional path;
writing one in would point at nothing. Null means "raw analysis not captured", which
readers must tolerate.

`files` is system-versioned, so versioning is switched off around the DDL and the history
table gets the matching column — same shape as migration 004.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE files SET (SYSTEM_VERSIONING = OFF)")

    op.add_column(
        "files",
        sa.Column(
            "analysis_blob_ref",
            sa.String(1024),
            nullable=True,
            comment=(
                "Blob storage path for the verbatim Document Intelligence response "
                "(e.g., tenant_id/file_id/analysis.json). Null when not captured."
            ),
        ),
    )

    # History table columns must match the main table's type exactly (VARCHAR, not NVARCHAR).
    op.execute("ALTER TABLE files_history ADD analysis_blob_ref VARCHAR(1024) NULL")

    op.execute(
        "ALTER TABLE files SET (SYSTEM_VERSIONING = ON (HISTORY_TABLE = dbo.files_history))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE files SET (SYSTEM_VERSIONING = OFF)")

    op.drop_column("files", "analysis_blob_ref")
    op.execute("ALTER TABLE files_history DROP COLUMN analysis_blob_ref")

    op.execute(
        "ALTER TABLE files SET (SYSTEM_VERSIONING = ON (HISTORY_TABLE = dbo.files_history))"
    )
