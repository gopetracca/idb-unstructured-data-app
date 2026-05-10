"""DTOs for collection management operations."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CreateCollectionInput(BaseModel):
    """Input DTO for creating a collection."""

    tenant_id: str = Field(..., description="Tenant identifier")
    name: str = Field(..., description="Collection name", min_length=1, max_length=100)
    vector_dimension: int = Field(
        ..., description="Vector dimension size", ge=1, le=4096
    )
    embedding_model: str = Field(
        ...,
        description="Embedding model used for this collection (e.g., 'text-embedding-3-small')",
        min_length=1,
        max_length=1536
    )
    document_type: str = Field(
        "operational",
        description="Document type schema to use (e.g., 'operational', 'publication')",
    )
    description: str | None = Field(None, description="Optional collection description")
    correlation_id: str = Field(..., description="Correlation ID for tracing")


class CreateCollectionOutput(BaseModel):
    """Output DTO for collection creation result."""

    name: str = Field(..., description="Collection name")
    vector_dimension: int = Field(..., description="Vector dimension size")
    embedding_model: str = Field(..., description="Embedding model for this collection")
    status: str = Field(..., description="Creation status")
    created_at: datetime = Field(..., description="Creation timestamp")
    correlation_id: str = Field(..., description="Correlation ID")


class CollectionInfo(BaseModel):
    """DTO for collection metadata."""

    name: str = Field(..., description="Collection name")
    vector_dimension: int | None = Field(None, description="Vector dimension size")
    embedding_model: str | None = Field(None, description="Embedding model for this collection")
    document_count: int = Field(..., ge=0, description="Number of documents")
    created_at: datetime | None = Field(None, description="Creation timestamp")


class ListCollectionsOutput(BaseModel):
    """Output DTO for listing collections."""

    collections: list[CollectionInfo] = Field(
        default_factory=list, description="List of collections"
    )
    total_count: int = Field(..., ge=0, description="Total number of collections")
    correlation_id: str = Field(..., description="Correlation ID")


class GetCollectionInput(BaseModel):
    """Input DTO for getting collection details."""

    tenant_id: str = Field(..., description="Tenant identifier")
    collection_name: str = Field(..., description="Collection name")
    correlation_id: str = Field(..., description="Correlation ID for tracing")


class GetCollectionOutput(BaseModel):
    """Output DTO for collection details."""

    name: str = Field(..., description="Collection name")
    vector_dimension: int | None = Field(None, description="Vector dimension size")
    embedding_model: str | None = Field(None, description="Embedding model for this collection")
    document_count: int = Field(..., ge=0, description="Number of documents")
    index_schema: dict[str, Any] = Field(..., description="Collection schema")
    created_at: datetime | None = Field(None, description="Creation timestamp")
    last_updated: datetime | None = Field(None, description="Last update timestamp")
    correlation_id: str = Field(..., description="Correlation ID")


class ConfigureRerankerInput(BaseModel):
    """Input DTO for enabling or disabling the reranker on a collection."""

    tenant_id: str = Field(..., description="Tenant identifier")
    collection_name: str = Field(..., description="Collection name")
    enabled: bool = Field(..., description="True to enable the reranker, False to disable")
    semantic_configuration_name: str | None = Field(
        None,
        description="Semantic configuration name override (uses service default when None)",
    )
    correlation_id: str = Field(..., description="Correlation ID for tracing")


class ConfigureRerankerOutput(BaseModel):
    """Output DTO for reranker configuration result."""

    collection_name: str = Field(..., description="Collection name")
    reranker_enabled: bool = Field(..., description="Whether the reranker is now enabled")
    semantic_configuration_name: str | None = Field(
        None, description="Active semantic configuration name (None when disabled)"
    )
    correlation_id: str = Field(..., description="Correlation ID")


class DeleteCollectionInput(BaseModel):
    """Input DTO for deleting a collection."""

    tenant_id: str = Field(..., description="Tenant identifier")
    collection_name: str = Field(..., description="Collection name to delete")
    correlation_id: str = Field(..., description="Correlation ID for tracing")


class DeleteCollectionOutput(BaseModel):
    """Output DTO for collection deletion result."""

    name: str = Field(..., description="Deleted collection name")
    status: str = Field(..., description="Deletion status")
    documents_deleted: int = Field(..., ge=0, description="Number of documents deleted")
    correlation_id: str = Field(..., description="Correlation ID")
