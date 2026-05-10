"""DTOs for vectorization operations."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_serializer

from src.application.dto.document_analysis import ProcessingStatus


class EmbeddingModel(StrEnum):
    """Supported embedding models."""

    EMBEDDING_3_SMALL = "text-embedding-3-small"
    EMBEDDING_3_LARGE = "text-embedding-3-large"


class VectorizeChunksRequest(BaseModel):
    """Request DTO for vectorizing document chunks."""

    file_id: str = Field(..., description="File identifier")
    tenant_id: str = Field(default="default", description="Tenant identifier")
    file_version: int = Field(default=1, ge=1, description="File version")
    source_container: str = Field(default="chunks", description="Source container for chunks")
    output_container: str = Field(default="embeddings", description="Output container for embeddings")
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Embedding model to use",
    )
    batch_size: int = Field(default=50, ge=1, le=100, description="Batch size for API calls")
    correlation_id: str | None = Field(default=None, description="Correlation ID for tracing")


class VectorizeChunksResult(BaseModel):
    """Result DTO for vectorizing chunks."""

    file_id: str = Field(..., description="File identifier")
    status: ProcessingStatus = Field(..., description="Processing status")
    total_chunks: int = Field(default=0, ge=0, description="Total chunks processed")
    embedded_chunks: int = Field(default=0, ge=0, description="Successfully embedded chunks")
    failed_chunks: int = Field(default=0, ge=0, description="Failed chunk embeddings")
    embedding_model: str = Field(..., description="Model used for embeddings")
    embedding_dimension: int = Field(..., ge=1, description="Vector dimension")
    embeddings_url: str | None = Field(default=None, description="URL to embeddings in blob storage")
    correlation_id: str = Field(..., description="Correlation ID for tracing")
    processing_time_ms: int | None = Field(default=None, description="Processing time in milliseconds")
    error_message: str | None = Field(default=None, description="Error message if failed")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Result creation timestamp")


class EmbeddingDTO(BaseModel):
    """DTO for embedding data (excludes full vector for list responses)."""

    chunk_id: str = Field(..., description="Chunk identifier")
    embedding_model: str = Field(..., description="Model used for embedding")
    embedding_dimension: int = Field(..., ge=1, description="Vector dimension")
    vector_preview: list[float] = Field(..., description="First 5 elements of vector")
    chunk_text_preview: str = Field(..., description="First 100 chars of chunk text")
    token_count: int = Field(..., ge=0, description="Token count")


class ListEmbeddingsRequest(BaseModel):
    """Request DTO for listing embeddings."""

    file_id: str = Field(..., description="File identifier")
    tenant_id: str = Field(default="default", description="Tenant identifier")
    file_version: int = Field(default=1, ge=1, description="File version")
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")


class ListEmbeddingsResult(BaseModel):
    """Result DTO for listing embeddings."""

    file_id: str = Field(..., description="File identifier")
    embedding_count: int = Field(..., ge=0, description="Total number of embeddings")
    embeddings: list[EmbeddingDTO] = Field(default_factory=list, description="List of embeddings")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, description="Items per page")
    total_pages: int = Field(..., ge=0, description="Total number of pages")

    @model_serializer
    def serialize_model(self) -> dict[str, Any]:
        """Serialize with pagination nested under a 'pagination' key."""
        return {
            "file_id": self.file_id,
            "embedding_count": self.embedding_count,
            "embeddings": [e.model_dump() for e in self.embeddings],
            "pagination": {
                "page": self.page,
                "page_size": self.page_size,
                "total_pages": self.total_pages,
            },
        }
