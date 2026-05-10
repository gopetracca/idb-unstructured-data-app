"""DTOs for document ingestion operations."""

from typing import Any

from pydantic import BaseModel, Field


class IngestionDocument(BaseModel):
    """DTO for a single document to ingest."""

    id: str = Field(..., description="Unique document identifier")
    chunk_id: str = Field(..., description="Chunk identifier")
    file_id: str = Field(..., description="File identifier")
    text: str = Field(..., description="Document text content")
    vector: list[float] = Field(..., description="Embedding vector")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Document metadata"
    )


class IngestDocumentsInput(BaseModel):
    """Input DTO for ingesting documents into a collection."""

    tenant_id: str = Field(..., description="Tenant identifier")
    collection_name: str = Field(..., description="Target collection name")
    documents: list[IngestionDocument] = Field(
        ..., description="Documents to ingest", min_length=1
    )
    correlation_id: str = Field(..., description="Correlation ID for tracing")


class IngestDocumentsOutput(BaseModel):
    """Output DTO for document ingestion result."""

    collection_name: str = Field(..., description="Collection name")
    total_documents: int = Field(..., ge=0, description="Total documents processed")
    successful: int = Field(..., ge=0, description="Successfully ingested")
    failed: int = Field(..., ge=0, description="Failed to ingest")
    failed_ids: list[str] = Field(
        default_factory=list, description="IDs of failed documents"
    )
    processing_time_ms: int = Field(..., ge=0, description="Processing time in ms")
    correlation_id: str = Field(..., description="Correlation ID")
