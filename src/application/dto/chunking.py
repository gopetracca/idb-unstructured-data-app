"""DTOs for document chunking operations."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_serializer

from src.application.dto.document_analysis import ProcessingStatus
from src.core.value_objects.chunking_strategy import ChunkingStrategy


class ChunkDocumentRequest(BaseModel):
    """Request DTO for document chunking."""

    file_id: str = Field(..., description="Unique file identifier")
    tenant_id: str = Field(default="default", description="Tenant identifier")
    source_container: str = Field(default="text", description="Source blob container (text)")
    output_container: str = Field(default="chunks", description="Output blob container (chunks)")
    chunking_strategy: ChunkingStrategy = Field(
        default_factory=ChunkingStrategy,
        description="Chunking strategy configuration. Defaults to fixed_size(512, 50).",
    )
    correlation_id: str | None = Field(
        default=None, description="Optional correlation ID for tracing"
    )


class ChunkDTO(BaseModel):
    """DTO for a single chunk."""

    chunk_id: str = Field(..., description="Unique chunk identifier")
    chunk_index: int = Field(..., ge=0, description="Position in file (0-based)")
    text_preview: str = Field(..., description="Preview of chunk text (first 100 chars)")
    char_count: int = Field(..., ge=0, description="Character count")
    start_char: int = Field(..., ge=0, description="Start position in source")
    end_char: int = Field(..., ge=0, description="End position in source")
    page_number: int | None = Field(default=None, description="Source page number")


class ChunkDocumentResult(BaseModel):
    """Result DTO for document chunking."""

    file_id: str = Field(..., description="Unique file identifier")
    status: ProcessingStatus = Field(..., description="Processing status")
    chunk_count: int = Field(default=0, ge=0, description="Number of chunks created")
    chunks_url: str | None = Field(
        default=None, description="URL to the chunks output directory"
    )
    chunking_strategy: str = Field(
        default="fixed_size", description="Chunking strategy used"
    )
    correlation_id: str = Field(..., description="Correlation ID for tracing")
    processing_time_ms: int | None = Field(
        default=None, description="Processing time in milliseconds"
    )
    error_message: str | None = Field(
        default=None, description="Error message if processing failed"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Timestamp of result creation"
    )


class ListChunksRequest(BaseModel):
    """Request DTO for listing chunks."""

    file_id: str = Field(..., description="File identifier")
    tenant_id: str = Field(default="default", description="Tenant identifier")
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")


class ListChunksResult(BaseModel):
    """Result DTO for listing chunks."""

    file_id: str = Field(..., description="File identifier")
    chunk_count: int = Field(..., ge=0, description="Total number of chunks")
    chunks: list[ChunkDTO] = Field(default_factory=list, description="List of chunks")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, description="Items per page")
    total_pages: int = Field(..., ge=0, description="Total number of pages")

    @model_serializer
    def serialize_model(self) -> dict[str, Any]:
        """Serialize with pagination nested under a 'pagination' key."""
        return {
            "file_id": self.file_id,
            "chunk_count": self.chunk_count,
            "chunks": [c.model_dump() for c in self.chunks],
            "pagination": {
                "page": self.page,
                "page_size": self.page_size,
                "total_pages": self.total_pages,
            },
        }
