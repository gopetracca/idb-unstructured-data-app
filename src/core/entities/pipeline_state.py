"""PipelineState entity for document processing state tracking.

Maps 1:1 to the `pipeline_state` SQL table. Owns all mutable processing
state and state transition business logic.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ProcessingStage(StrEnum):
    """Processing stages for document pipeline."""

    DISPATCHER = "dispatcher"
    CONVERT = "convert"
    CHUNK = "chunk"
    VECTORIZE = "vectorize"
    INGEST = "ingest"
    COMPLETED = "completed"


class OverallStatus(StrEnum):
    """Overall status of file processing."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineState(BaseModel):
    """Processing pipeline state — maps to `pipeline_state` table.

    Tracks the current processing stage, status, error state, and
    pipeline configuration for a document in the RAG pipeline.
    """

    # FK to files table
    file_id: str = Field(..., description="File identifier (FK to files)")

    # Processing state
    current_stage: ProcessingStage = Field(
        default=ProcessingStage.DISPATCHER,
        description="Current processing stage",
    )
    overall_status: OverallStatus = Field(
        default=OverallStatus.QUEUED,
        description="Overall processing status",
    )

    # Chunk tracking (denormalized for performance)
    chunk_count: int = Field(default=0, ge=0, description="Number of chunks")
    embedded_chunk_count: int = Field(default=0, ge=0, description="Chunks with embeddings")

    # Error handling
    error_message: str = Field(default="", description="Last error message")
    retry_count: int = Field(default=0, ge=0, description="Number of retry attempts")
    last_updated: datetime = Field(
        default_factory=datetime.utcnow, description="Last modification time"
    )

    # Pipeline configuration
    chunking_strategy: str = Field(default="", description="Chunking strategy used")
    embedding_model: str = Field(default="", description="Embedding model used")
    vector_db_targets: str = Field(default="[]", description="Target DBs as JSON array")

    def mark_processing(self, stage: ProcessingStage) -> None:
        """Update to processing state at given stage."""
        self.current_stage = stage
        self.overall_status = OverallStatus.PROCESSING
        self.last_updated = datetime.utcnow()

    def mark_completed(self) -> None:
        """Mark processing as completed."""
        self.current_stage = ProcessingStage.COMPLETED
        self.overall_status = OverallStatus.COMPLETED
        self.last_updated = datetime.utcnow()

    def mark_failed(self, error_message: str) -> None:
        """Mark processing as failed with error."""
        self.overall_status = OverallStatus.FAILED
        self.error_message = error_message
        self.retry_count += 1
        self.last_updated = datetime.utcnow()
