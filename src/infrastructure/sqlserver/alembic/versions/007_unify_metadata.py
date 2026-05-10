"""Unify metadata architecture — remove files.metadata_json, add columns to file_metadata.

Revision ID: 007
Revises: 006
Create Date: 2026-03-29

Changes:
- Add `source`, `department`, `description`, `tags` columns to `file_metadata` table
- Data migration: extract values from `files.metadata_json` into new columns
- Drop `metadata_json` column from `files` table

Related to issue #108: Unify metadata architecture
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add new columns to file_metadata
    op.add_column("file_metadata", sa.Column("source", sa.String(200), nullable=True))
    op.add_column("file_metadata", sa.Column("department", sa.String(200), nullable=True))
    op.add_column("file_metadata", sa.Column("description", sa.Text, nullable=True))
    op.add_column("file_metadata", sa.Column("tags", sa.JSON, nullable=True))

    # 2. Data migration: extract values from files.metadata_json into new columns
    conn = op.get_bind()

    rows = conn.execute(
        sa.text("SELECT file_id, metadata_json FROM files WHERE metadata_json IS NOT NULL AND metadata_json != '{}'")
    ).fetchall()

    for file_id, metadata_json_str in rows:
        if not metadata_json_str:
            continue
        try:
            data = json.loads(metadata_json_str)
        except (json.JSONDecodeError, TypeError):
            continue

        source = data.get("source")
        department = data.get("department")
        description = data.get("description")
        tags = data.get("tags")
        # Normalize tags to a list
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        if not isinstance(tags, list):
            tags = None

        # Only update if there is something to migrate
        if not any([source, department, description, tags]):
            continue

        conn.execute(
            sa.text(
                """
                UPDATE file_metadata
                SET source = :source,
                    department = :department,
                    description = :description,
                    tags = :tags
                WHERE file_id = :file_id
                """
            ),
            {
                "file_id": file_id,
                "source": source,
                "department": department,
                "description": description,
                "tags": json.dumps(tags) if tags is not None else None,
            },
        )

    # 3. Drop metadata_json column from files table
    #    SQL Server requires dropping any default constraint first.
    #    We use a dynamic query to find and drop the constraint name.
    conn.execute(
        sa.text(
            """
            DECLARE @constraintName NVARCHAR(256);
            SELECT @constraintName = dc.name
            FROM sys.default_constraints dc
            JOIN sys.columns c ON dc.parent_object_id = c.object_id
                               AND dc.parent_column_id = c.column_id
            JOIN sys.tables t ON c.object_id = t.object_id
            WHERE t.name = 'files' AND c.name = 'metadata_json';

            IF @constraintName IS NOT NULL
            BEGIN
                EXEC('ALTER TABLE files DROP CONSTRAINT [' + @constraintName + ']');
            END
            """
        )
    )
    op.drop_column("files", "metadata_json")


def downgrade() -> None:
    # Re-add metadata_json to files
    op.add_column(
        "files",
        sa.Column("metadata_json", sa.Text, nullable=False, server_default="{}"),
    )

    # Migrate data back from file_metadata to files.metadata_json
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT file_id, source, department, description, tags FROM file_metadata "
            "WHERE source IS NOT NULL OR department IS NOT NULL "
            "OR description IS NOT NULL OR tags IS NOT NULL"
        )
    ).fetchall()

    for file_id, source, department, description, tags_json in rows:
        data: dict = {}
        if source:
            data["source"] = source
        if department:
            data["department"] = department
        if description:
            data["description"] = description
        if tags_json:
            try:
                data["tags"] = json.loads(tags_json) if isinstance(tags_json, str) else tags_json
            except (json.JSONDecodeError, TypeError):
                pass
        if data:
            conn.execute(
                sa.text("UPDATE files SET metadata_json = :json WHERE file_id = :file_id"),
                {"json": json.dumps(data), "file_id": file_id},
            )

    # Drop migrated columns from file_metadata
    op.drop_column("file_metadata", "tags")
    op.drop_column("file_metadata", "description")
    op.drop_column("file_metadata", "department")
    op.drop_column("file_metadata", "source")
