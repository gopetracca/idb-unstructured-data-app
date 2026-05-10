"""SQLAlchemy model for the pipeline_state table."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.entities.pipeline_state import PipelineState
from src.infrastructure.sqlserver.models.base import Base

if TYPE_CHECKING:
    from src.core.entities.file_index import FileIndex


class PipelineStateTable(Base):
    """ORM model for the `pipeline_state` table.

    Maps to the PipelineState entity. Holds all mutable processing state
    for a document in the RAG pipeline.
    """

    __tablename__ = "pipeline_state"

    # Identity (FK to files)
    file_id: Mapped[str] = mapped_column(
        sa.String(36),
        sa.ForeignKey("files.file_id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Processing state
    current_stage: Mapped[str] = mapped_column(
        sa.String(32), nullable=False, server_default="dispatcher"
    )
    overall_status: Mapped[str] = mapped_column(
        sa.String(32), nullable=False, server_default="queued"
    )

    # Chunk tracking (denormalized for performance)
    chunk_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    embedded_chunk_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )

    # Error handling
    error_message: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="")
    retry_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")

    # Audit timestamp
    last_updated: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()
    )

    # Pipeline configuration
    chunking_strategy: Mapped[str] = mapped_column(
        sa.Text, nullable=False, server_default=""
    )
    embedding_model: Mapped[str] = mapped_column(
        sa.String(100), nullable=False, server_default=""
    )
    vector_db_targets: Mapped[str] = mapped_column(
        sa.Text, nullable=False, server_default="[]"
    )

    # Relationship
    file: Mapped["FileTable"] = relationship(
        "FileTable", back_populates="pipeline_state"
    )

    # Indexes
    __table_args__ = (
        sa.Index("ix_pipeline_state_status", "overall_status", "current_stage"),
    )

    # Fields excluded from update_from_entity (immutable identity)
    _UPDATE_EXCLUDE = frozenset({"file_id"})

    def to_entity(self) -> PipelineState:
        """Convert ORM model to PipelineState entity."""
        return PipelineState.model_validate(self, from_attributes=True)

    @classmethod
    def from_entity(cls, entity: PipelineState) -> "PipelineStateTable":
        """Create ORM model from PipelineState entity."""
        return cls(**entity.model_dump())

    def update_from_entity(self, entity: PipelineState) -> None:
        """Update ORM model fields from a PipelineState entity."""
        for field, value in entity.model_dump(exclude=self._UPDATE_EXCLUDE).items():
            setattr(self, field, value)

    _PIPELINE_FIELDS = frozenset({
        "current_stage", "overall_status", "chunk_count", "embedded_chunk_count",
        "chunking_strategy", "embedding_model", "vector_db_targets",
        "error_message", "retry_count",
    })

    @classmethod
    def from_file_index(cls, fi: FileIndex) -> PipelineStateTable:
        """Create a PipelineStateTable row from the pipeline portion of a FileIndex."""
        data = fi.model_dump(include=cls._PIPELINE_FIELDS)
        data["file_id"] = fi.file_id
        return cls(**data)

    def update_from_file_index(self, fi: FileIndex) -> None:
        """Update pipeline columns from a FileIndex entity."""
        fi_data = fi.model_dump(include=self._PIPELINE_FIELDS)
        for field, value in fi_data.items():
            setattr(self, field, value)


# Forward reference
from src.infrastructure.sqlserver.models.file_model import FileTable  # noqa: E402
