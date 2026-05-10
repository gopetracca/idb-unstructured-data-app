"""HTTP schemas for document vectorization endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field


class VectorizeChunksRequestSchema(BaseModel):
    """Request schema for vectorizing document chunks."""

    file_id: str = Field(..., description="File identifier (UUID)")
    tenant_id: str = Field(default="default", description="Tenant identifier")
    file_version: int = Field(default=1, ge=1, description="File version")
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Embedding model to use",
    )
    batch_size: int = Field(
        default=50,
        ge=1,
        le=100,
        description="Batch size for API calls",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "file_id": "550e8400-e29b-41d4-a716-446655440000",
                    "tenant_id": "default",
                    "file_version": 1,
                    "embedding_model": "text-embedding-3-small",
                    "batch_size": 50,
                }
            ]
        }
    }


class VectorizeChunksResponseSchema(BaseModel):
    """Response schema for vectorization result."""

    file_id: str = Field(..., description="File identifier")
    status: str = Field(..., description="Processing status (completed/failed)")
    total_chunks: int = Field(..., ge=0, description="Total chunks processed")
    embedded_chunks: int = Field(..., ge=0, description="Successfully embedded chunks")
    failed_chunks: int = Field(..., ge=0, description="Failed chunk embeddings")
    embedding_model: str = Field(..., description="Model used for embeddings")
    embedding_dimension: int = Field(..., ge=1, description="Vector dimension")
    embeddings_url: str | None = Field(
        default=None,
        description="URL to embeddings in blob storage",
    )
    correlation_id: str = Field(..., description="Correlation ID for tracing")
    processing_time_ms: int | None = Field(
        default=None,
        description="Processing time in milliseconds",
    )
    error_message: str | None = Field(
        default=None,
        description="Error message if failed",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp of response creation",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "file_id": "550e8400-e29b-41d4-a716-446655440000",
                    "status": "completed",
                    "total_chunks": 25,
                    "embedded_chunks": 25,
                    "failed_chunks": 0,
                    "embedding_model": "text-embedding-3-small",
                    "embedding_dimension": 1536,
                    "embeddings_url": "embeddings/550e8400-e29b-41d4-a716-446655440000/",
                    "correlation_id": "abc-123-def",
                    "processing_time_ms": 5000,
                    "error_message": None,
                    "created_at": "2026-01-28T10:00:00Z",
                }
            ]
        }
    }


class EmbeddingSchema(BaseModel):
    """Schema for individual embedding (list view)."""

    chunk_id: str = Field(..., description="Chunk identifier")
    embedding_model: str = Field(..., description="Model used for embedding")
    embedding_dimension: int = Field(..., ge=1, description="Vector dimension")
    vector_preview: list[float] = Field(..., description="First 5 elements of vector")
    chunk_text_preview: str = Field(..., description="First 100 chars of chunk text")
    token_count: int = Field(..., ge=0, description="Token count")


class PaginationSchema(BaseModel):
    """Schema for pagination information."""

    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, description="Items per page")
    total_pages: int = Field(..., ge=0, description="Total number of pages")


class ListEmbeddingsResponseSchema(BaseModel):
    """Response schema for listing embeddings."""

    file_id: str = Field(..., description="File identifier")
    embedding_count: int = Field(..., ge=0, description="Total number of embeddings")
    embeddings: list[EmbeddingSchema] = Field(
        default_factory=list,
        description="List of embeddings",
    )
    pagination: PaginationSchema = Field(..., description="Pagination information")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "file_id": "550e8400-e29b-41d4-a716-446655440000",
                    "embedding_count": 25,
                    "embeddings": [
                        {
                            "chunk_id": "550e8400-e29b-41d4-a716-446655440000_chunk_0",
                            "embedding_model": "text-embedding-3-small",
                            "embedding_dimension": 1536,
                            "vector_preview": [0.1, -0.2, 0.3, 0.1, -0.1],
                            "chunk_text_preview": "This is the beginning of the document...",
                            "token_count": 128,
                        }
                    ],
                    "pagination": {
                        "page": 1,
                        "page_size": 20,
                        "total_pages": 2,
                    },
                }
            ]
        }
    }


class SupportedModelsResponseSchema(BaseModel):
    """Response schema for supported embedding models."""

    models: list[str] = Field(..., description="List of supported model names")
    default_model: str = Field(..., description="Default model name")
    model_dimensions: dict[str, int] = Field(
        ...,
        description="Mapping of model names to vector dimensions",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "models": ["text-embedding-3-small", "text-embedding-3-large"],
                    "default_model": "text-embedding-3-small",
                    "model_dimensions": {
                        "text-embedding-3-small": 1536,
                        "text-embedding-3-large": 3072,
                    },
                }
            ]
        }
    }
