"""SQLAlchemy model for the chunk_vector_refs table."""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.sqlserver.models.base import Base


class ChunkVectorRefTable(Base):
    """ORM model for the `chunk_vector_refs` table.

    Tracks which vector database contains a given chunk's embedding.
    """

    __tablename__ = "chunk_vector_refs"

    chunk_id: Mapped[str] = mapped_column(
        sa.String(200),
        sa.ForeignKey("chunks.chunk_id", ondelete="CASCADE"),
        primary_key=True,
    )
    db_name: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    vector_doc_id: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, server_default=sa.func.now()
    )

    # Relationship
    chunk: Mapped["ChunkTable"] = relationship(
        "ChunkTable", back_populates="vector_refs"
    )

    # Indexes
    __table_args__ = (
        sa.Index("ix_vector_refs_db_doc", "db_name", "vector_doc_id"),
    )


from src.infrastructure.sqlserver.models.chunk_model import ChunkTable  # noqa: E402
