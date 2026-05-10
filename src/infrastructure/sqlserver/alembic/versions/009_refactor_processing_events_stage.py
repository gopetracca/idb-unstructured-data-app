"""Refactor processing_events: replace from_stage/to_stage with stage.

Revision ID: 009
Revises: 008
Create Date: 2026-04-27

Changes:
- Drop `from_stage` column
- Rename `to_stage` column to `stage`
- Update index `ix_events_tenant_stage` to reference `stage`
"""

from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the old composite index that references to_stage before renaming
    op.drop_index("ix_events_tenant_stage", table_name="processing_events")

    # Drop from_stage column
    op.drop_column("processing_events", "from_stage")

    # Rename to_stage -> stage
    op.alter_column(
        "processing_events",
        "to_stage",
        new_column_name="stage",
        existing_type=sa.String(32),
        existing_nullable=False,
    )

    # Recreate index with new column name
    op.create_index(
        "ix_events_tenant_stage",
        "processing_events",
        ["tenant_id", "stage", "event_timestamp"],
    )


def downgrade() -> None:
    op.drop_index("ix_events_tenant_stage", table_name="processing_events")

    op.alter_column(
        "processing_events",
        "stage",
        new_column_name="to_stage",
        existing_type=sa.String(32),
        existing_nullable=False,
    )

    op.add_column(
        "processing_events",
        sa.Column("from_stage", sa.String(32), nullable=True),
    )

    op.create_index(
        "ix_events_tenant_stage",
        "processing_events",
        ["tenant_id", "to_stage", "event_timestamp"],
    )
