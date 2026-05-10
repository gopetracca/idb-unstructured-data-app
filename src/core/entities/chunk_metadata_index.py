"""ChunkMetadataIndex entity for chunk processing metadata."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EmbeddingStatus(StrEnum):
    """Status of chunk embedding."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class ChunkMetadataIndex(BaseModel):
    """
    Processing metadata for a chunk, stored separately from core chunk data.

    Mirrors the files/file_metadata pattern: core positional data lives in
    ChunkIndex (chunks table), while processing state lives here
    (chunk_metadata table).
    """

    chunk_id: str = Field(..., description="Chunk identifier (FK to chunks)")

    # Processing state
    embedding_status: EmbeddingStatus = Field(
        default=EmbeddingStatus.PENDING,
        description="Status of embedding generation",
    )

    # Flexible metadata blob (section_path, has_table, table_id, token_count, etc.)
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        description="Chunk-specific metadata as JSON object",
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Creation time",
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Last update time",
    )

    def mark_embedded(self) -> None:
        """Mark chunk embedding as completed."""
        self.embedding_status = EmbeddingStatus.COMPLETED
        self.updated_at = datetime.utcnow()

    def mark_failed(self) -> None:
        """Mark chunk embedding as failed."""
        self.embedding_status = EmbeddingStatus.FAILED
        self.updated_at = datetime.utcnow()
