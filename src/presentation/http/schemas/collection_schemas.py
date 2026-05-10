"""HTTP schemas for collection management endpoints."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CreateCollectionRequest(BaseModel):
    """Request schema for creating a collection."""

    name: str = Field(
        ...,
        description="Collection name",
        min_length=1,
        max_length=100,
        pattern="^[a-zA-Z0-9-_]+$",
    )
    vector_dimension: int = Field(
        ...,
        description="Vector dimension size (e.g., 1536 for text-embedding-3-small)",
        ge=1,
        le=4096,
    )
    embedding_model: str = Field(
        ...,
        description="Embedding model to use for this collection (e.g., 'text-embedding-3-small')",
        min_length=1,
        max_length=100,
    )
    document_type: str = Field(
        "operational",
        description="Document type schema to use (e.g., 'operational', 'publication')",
        min_length=1,
        max_length=50,
    )
    description: str | None = Field(
        None,
        description="Optional collection description",
        max_length=500,
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "embeddings",
                    "vector_dimension": 1536,
                    "embedding_model": "text-embedding-3-small",
                    "document_type": "operational",
                    "description": "Document embeddings for semantic search",
                }
            ]
        }
    }


class CreateCollectionResponse(BaseModel):
    """Response schema for collection creation."""

    name: str = Field(..., description="Collection name")
    vector_dimension: int = Field(..., description="Vector dimension size")
    embedding_model: str = Field(..., description="Embedding model for this collection")
    status: str = Field(..., description="Creation status")
    created_at: datetime = Field(..., description="Creation timestamp")
    correlation_id: str = Field(..., description="Correlation ID for tracing")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "embeddings",
                    "vector_dimension": 1536,
                    "embedding_model": "text-embedding-3-small",
                    "status": "created",
                    "created_at": "2026-01-30T10:00:00Z",
                    "correlation_id": "abc-123-def",
                }
            ]
        }
    }


class CollectionSchema(BaseModel):
    """Schema for collection metadata in list view."""

    name: str = Field(..., description="Collection name")
    vector_dimension: int | None = Field(None, description="Vector dimension size")
    embedding_model: str | None = Field(None, description="Embedding model for this collection")
    document_count: int = Field(..., ge=0, description="Number of documents")
    created_at: datetime | None = Field(None, description="Creation timestamp")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "embeddings",
                    "vector_dimension": 1536,
                    "embedding_model": "text-embedding-3-small",
                    "document_count": 1250,
                    "created_at": "2026-01-30T10:00:00Z",
                }
            ]
        }
    }


class ListCollectionsResponse(BaseModel):
    """Response schema for listing collections."""

    collections: list[CollectionSchema] = Field(
        default_factory=list, description="List of collections"
    )
    total_count: int = Field(..., ge=0, description="Total number of collections")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "collections": [
                        {
                            "name": "embeddings",
                            "vector_dimension": 1536,
                            "document_count": 1250,
                            "created_at": "2026-01-30T10:00:00Z",
                        }
                    ],
                    "total_count": 1,
                }
            ]
        }
    }


class GetCollectionResponse(BaseModel):
    """Response schema for getting collection details."""

    name: str = Field(..., description="Collection name")
    vector_dimension: int | None = Field(None, description="Vector dimension size")
    embedding_model: str | None = Field(None, description="Embedding model for this collection")
    document_count: int = Field(..., ge=0, description="Number of documents")
    index_schema: dict[str, Any] = Field(..., description="Collection schema")
    created_at: datetime | None = Field(None, description="Creation timestamp")
    last_updated: datetime | None = Field(None, description="Last update timestamp")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "embeddings",
                    "vector_dimension": 1536,
                    "embedding_model": "text-embedding-3-small",
                    "document_count": 1250,
                    "index_schema": {
                        "fields": [
                            "id",
                            "chunkId",
                            "fileId",
                            "content",
                            "contentVector",
                            "metadata",
                        ]
                    },
                    "created_at": "2026-01-30T10:00:00Z",
                    "last_updated": "2026-01-30T12:00:00Z",
                }
            ]
        }
    }


class DeleteCollectionResponse(BaseModel):
    """Response schema for deleting a collection."""

    name: str = Field(..., description="Deleted collection name")
    status: str = Field(..., description="Deletion status")
    documents_deleted: int = Field(..., ge=0, description="Number of documents deleted")
    correlation_id: str = Field(..., description="Correlation ID for tracing")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "embeddings",
                    "status": "deleted",
                    "documents_deleted": 1250,
                    "correlation_id": "abc-123-def",
                }
            ]
        }
    }


class ConfigureRerankerRequest(BaseModel):
    """Request schema for enabling or disabling the reranker on a collection."""

    enabled: bool = Field(..., description="True to enable the reranker, False to disable")
    semantic_configuration_name: str | None = Field(
        None,
        description="Semantic configuration name override. Uses the service default when omitted.",
        max_length=100,
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"enabled": True},
                {"enabled": True, "semantic_configuration_name": "my-semantic-config"},
                {"enabled": False},
            ]
        }
    }


class ConfigureRerankerResponse(BaseModel):
    """Response schema for reranker configuration."""

    collection_name: str = Field(..., description="Collection name")
    reranker_enabled: bool = Field(..., description="Whether the reranker is now enabled")
    semantic_configuration_name: str | None = Field(
        None, description="Active semantic configuration name (null when disabled)"
    )
    correlation_id: str = Field(..., description="Correlation ID for tracing")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "collection_name": "np-d-aimvp-operational",
                    "reranker_enabled": True,
                    "semantic_configuration_name": "default-semantic-config",
                    "correlation_id": "abc-123-def",
                }
            ]
        }
    }


class DocumentSchema(BaseModel):
    """Schema for a single document in ingestion request."""

    id: str = Field(..., description="Unique document identifier (e.g., file123_chunk-0)")
    chunk_id: str = Field(..., description="Chunk identifier")
    file_id: str = Field(..., description="File identifier")
    text: str = Field(..., description="Document text content", min_length=1)
    vector: list[float] = Field(
        ...,
        description="Embedding vector",
        min_length=1,
        max_length=4096,
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Document metadata (e.g., model_version, token_count)",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "file123_chunk-0",
                    "chunk_id": "chunk-0",
                    "file_id": "file123",
                    "text": "Document text content...",
                    "vector": [0.1, -0.2, 0.3],
                    "metadata": {
                        "model_version": "text-embedding-3-small",
                        "token_count": 128,
                        "chunking_strategy": "sentence",
                        "chunk_size": 512,
                        "overlap_chars": 50,
                    },
                }
            ]
        }
    }


class IngestDocumentsRequest(BaseModel):
    """Request schema for ingesting documents."""

    documents: list[DocumentSchema] = Field(
        ...,
        description="Documents to ingest",
        min_length=1,
        max_length=1000,
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "documents": [
                        {
                            "id": "file123_chunk-0",
                            "chunk_id": "chunk-0",
                            "file_id": "file123",
                            "text": "Document text content...",
                            "vector": [0.1, -0.2, 0.3],
                            "metadata": {
                                "model_version": "text-embedding-3-small",
                                "token_count": 128,
                            },
                        }
                    ]
                }
            ]
        }
    }


class IngestDocumentsResponse(BaseModel):
    """Response schema for document ingestion."""

    collection_name: str = Field(..., description="Collection name")
    total_documents: int = Field(..., ge=0, description="Total documents processed")
    successful: int = Field(..., ge=0, description="Successfully ingested")
    failed: int = Field(..., ge=0, description="Failed to ingest")
    failed_ids: list[str] = Field(
        default_factory=list, description="IDs of failed documents"
    )
    processing_time_ms: int = Field(..., ge=0, description="Processing time in ms")
    correlation_id: str = Field(..., description="Correlation ID for tracing")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "collection_name": "embeddings",
                    "total_documents": 100,
                    "successful": 100,
                    "failed": 0,
                    "failed_ids": [],
                    "processing_time_ms": 150,
                    "correlation_id": "abc-123-def",
                }
            ]
        }
    }
