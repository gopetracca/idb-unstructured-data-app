"""SQLAlchemy model for the chunk_metadata table."""

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.entities.chunk_metadata_index import ChunkMetadataIndex
from src.infrastructure.sqlserver.models.base import Base


class ChunkMetadataTable(Base):
    """ORM model for the `chunk_metadata` table.

    Stores processing metadata for chunks (embedding status, flexible JSON),
    mirroring the files/file_metadata pattern.
    """

    __tablename__ = "chunk_metadata"

    chunk_id: Mapped[str] = mapped_column(
        sa.String(200),
        sa.ForeignKey("chunks.chunk_id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Processing state
    embedding_status: Mapped[str] = mapped_column(
        sa.String(32), nullable=False, server_default="pending"
    )

    # Flexible metadata blob
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        sa.JSON, nullable=False, server_default=sa.text("'{}'")
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()
    )

    # Relationship
    chunk: Mapped["ChunkTable"] = relationship(
        "ChunkTable", back_populates="metadata_record"
    )

    # Indexes
    __table_args__ = (
        sa.Index("ix_chunk_metadata_status", "embedding_status"),
    )

    # Fields excluded from update_from_entity (immutable identity + timestamps)
    _UPDATE_EXCLUDE = frozenset({"chunk_id", "created_at"})

    def to_entity(self) -> ChunkMetadataIndex:
        """Convert ORM model to core ChunkMetadataIndex entity."""
        return ChunkMetadataIndex.model_validate(self, from_attributes=True)

    @classmethod
    def from_entity(cls, entity: ChunkMetadataIndex) -> "ChunkMetadataTable":
        """Create ORM model from core ChunkMetadataIndex entity."""
        return cls(**entity.model_dump())

    def update_from_entity(self, entity: ChunkMetadataIndex) -> None:
        """Update ORM model fields from a ChunkMetadataIndex entity."""
        for field, value in entity.model_dump(exclude=self._UPDATE_EXCLUDE).items():
            setattr(self, field, value)


# Forward reference
from src.infrastructure.sqlserver.models.chunk_model import ChunkTable  # noqa: E402
