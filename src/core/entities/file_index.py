"""FileIndex entity for file-level state tracking."""

import re
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


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


class FileIndex(BaseModel):
    """
    FileIndex entity representing file-level state in the RAG pipeline.

    Combines processing state (stages, status) with all metadata fields
    stored as SQL columns (files + pipeline_state + file_metadata tables).
    """

    # Keys (required)
    tenant_id: str = Field(..., description="Tenant identifier (PartitionKey)")
    file_id: str = Field(..., description="Unique file identifier (RowKey)")

    # File metadata
    blob_name: str = Field(..., description="Original filename")
    content_type: str = Field(default="application/octet-stream", description="MIME type")
    size_bytes: int = Field(default=0, ge=0, description="File size in bytes")
    content_hash: str = Field(default="", description="SHA-256 hash of content")
    upload_timestamp: datetime = Field(default_factory=datetime.utcnow, description="Upload time")
    file_version: int = Field(default=1, ge=1, description="Version number")

    # Blob storage references (SSOT for content location)
    raw_blob_ref: str | None = Field(
        default=None,
        description="Blob storage path for raw uploaded file (e.g., tenant_id/file_id/filename)",
    )
    text_blob_ref: str | None = Field(
        default=None,
        description="Blob storage path for extracted text (e.g., tenant_id/file_id/text.json)",
    )

    # Processing state
    current_stage: ProcessingStage = Field(
        default=ProcessingStage.DISPATCHER,
        description="Current processing stage",
    )
    overall_status: OverallStatus = Field(
        default=OverallStatus.QUEUED,
        description="Overall processing status",
    )

    # Chunk tracking
    chunk_count: int = Field(default=0, ge=0, description="Number of chunks")
    embedded_chunk_count: int = Field(default=0, ge=0, description="Chunks with embeddings")

    # Processing configuration
    chunking_strategy: str = Field(default="", description="Chunking strategy used")
    embedding_model: str = Field(default="", description="Embedding model used")
    vector_db_targets: str = Field(default="[]", description="Target DBs as JSON array")

    # Error handling
    error_message: str = Field(default="", description="Last error message")
    retry_count: int = Field(default=0, ge=0, description="Number of retry attempts")
    last_updated: datetime = Field(default_factory=datetime.utcnow, description="Last modification time")

    # Collection and external identifiers (files table)
    collection_name: str | None = Field(
        default=None,
        description="Collection to which the document will be ingested",
    )
    ezshare_id: str | None = Field(
        default=None,
        max_length=100,
        description="External document management system ID (e.g., EZSHARE-510177122-450)",
    )

    # Promoted metadata fields (stored in file_metadata table for efficient filtering)
    # These fields map 1:1 to SQL columns — SQL is SSOT (ADR-005)
    document_category: str | None = Field(
        default=None,
        max_length=100,
        description="Schema discriminator: 'operational' or 'publication'",
    )
    document_type: str | None = Field(
        default=None,
        max_length=100,
        description="User-facing document classification (e.g., 'PCR', 'Report', 'LP')",
    )
    language: str | None = Field(
        default="en",
        max_length=10,
        description="ISO 639-1 language code",
    )
    operation_number: str | None = Field(
        default=None,
        max_length=50,
        description="Operation number (e.g., UR-P1180) - CRITICAL FIELD",
    )
    document_name: str | None = Field(
        default=None,
        max_length=500,
        description="Document display name",
    )
    document_author: str | None = Field(
        default=None,
        max_length=200,
        description="Primary document author",
    )
    document_url: str | None = Field(
        default=None,
        description="URL of the document",
    )
    disclosed: bool | None = Field(
        default=None,
        description="Disclosure status",
    )
    country: str | None = Field(
        default=None,
        max_length=100,
        description="Country code or name",
    )
    operation_type: str | None = Field(
        default=None,
        max_length=100,
        description="Operation classification",
    )
    dept_id: str | None = Field(
        default=None,
        max_length=100,
        description="Department ID (e.g., EXR/CMG)",
    )
    sector: str | None = Field(
        default=None,
        max_length=100,
        description="Sector classification (e.g., TRANSPORT)",
    )
    year: int | None = Field(
        default=None,
        ge=1900,
        le=2100,
        description="Publication year",
    )
    file_extension: str | None = Field(
        default=None,
        max_length=10,
        description="File extension (e.g., .pdf, .docx)",
    )
    access_to_information_policy: str | None = Field(
        default=None,
        description="If public or not",
    )
    document_publish_date: datetime | None = Field(
        default=None,
        description="Publication date",
    )
    document_approval_date: datetime | None = Field(
        default=None,
        description="Approval date",
    )
    document_created_date: datetime | None = Field(
        default=None,
        description="Created date",
    )
    # Migrated from files.metadata_json — now promoted SQL columns
    source: str | None = Field(default=None, max_length=200, description="Document source")
    department: str | None = Field(default=None, max_length=200, description="Organizational department")
    description: str | None = Field(default=None, description="Document description")
    tags: list[str] = Field(default_factory=list, description="Categorization tags")

    @field_validator("operation_number")
    @classmethod
    def validate_operation_number(cls, v: str | None) -> str | None:
        """Validate operation number format (e.g., UR-P1180)."""
        if v is not None and not re.match(r"^[A-Z]{2}-P\d+$", v):
            raise ValueError(
                "operation_number must follow format: XX-PNNNN (e.g., UR-P1180)"
            )
        return v

    @field_validator("file_extension")
    @classmethod
    def validate_file_extension(cls, v: str | None) -> str | None:
        """Ensure file extension starts with dot."""
        if v is not None and v and not v.startswith("."):
            return f".{v}"
        return v

    def mark_processing(self, stage: ProcessingStage) -> None:
        """Update to processing state at given stage."""
        self.current_stage = stage
        self.overall_status = OverallStatus.PROCESSING
        self.last_updated = datetime.utcnow()

    def mark_completed(self) -> None:
        """Mark file processing as completed."""
        self.current_stage = ProcessingStage.COMPLETED
        self.overall_status = OverallStatus.COMPLETED
        self.last_updated = datetime.utcnow()

    def mark_failed(self, error_message: str) -> None:
        """Mark file processing as failed with error."""
        self.overall_status = OverallStatus.FAILED
        self.error_message = error_message
        self.retry_count += 1
        self.last_updated = datetime.utcnow()
