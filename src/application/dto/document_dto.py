"""Data Transfer Objects for document operations."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.core.value_objects.chunking_strategy import ChunkingStrategy
from src.core.value_objects.document_metadata import DocumentMetadata


class DocumentDTO(BaseModel):
    """Standard document representation for API responses."""

    file_id: str = Field(..., description="Unique file identifier")
    filename: str = Field(..., description="Original filename")
    size_bytes: int = Field(..., description="File size in bytes")
    mime_type: str = Field(..., description="MIME type of the file")
    created_at: datetime = Field(..., description="Upload timestamp")
    updated_at: datetime = Field(..., description="Last modification timestamp")
    metadata: DocumentMetadata = Field(..., description="Document metadata")


class PaginationDTO(BaseModel):
    """Pagination information for list responses."""

    total_count: int = Field(..., ge=0, description="Total number of items")
    limit: int = Field(..., ge=1, description="Items per page")
    has_next: bool = Field(..., description="Whether there are more items")
    has_previous: bool = Field(..., description="Whether there are previous items")
    next_cursor: str | None = Field(None, description="Cursor for next page")
    previous_cursor: str | None = Field(None, description="Cursor for previous page")


# Upload Document DTOs
class UploadDocumentInput(BaseModel):
    """Input for upload document use case."""

    tenant_id: str = Field(..., description="Tenant identifier")
    filename: str = Field(..., description="Original filename")
    content: bytes = Field(..., description="File content as bytes")
    content_type: str = Field(..., description="MIME type of the file")
    collection_name: str = Field(..., description="Collection to ingest the document into")
    ezshare_id: str = Field(..., description="External document ID (e.g., EZSHARE-510177122-450)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="User-provided metadata")
    chunking_strategy: ChunkingStrategy = Field(
        default_factory=ChunkingStrategy,
        description=(
            "Typed chunking strategy configuration in nested shape "
            "{'strategy_name', 'parameters'}."
        ),
    )


class UploadDocumentOutput(BaseModel):
    """Output from upload document use case."""

    file_id: str = Field(..., description="Generated file identifier")
    filename: str = Field(..., description="Original filename")
    size_bytes: int = Field(..., description="File size in bytes")
    mime_type: str = Field(..., description="MIME type")
    uploaded_at: datetime = Field(..., description="Upload timestamp")
    metadata: DocumentMetadata = Field(..., description="Document metadata")


# Update Metadata DTOs
class UpdateMetadataInput(BaseModel):
    """Input for update metadata use case."""

    tenant_id: str = Field(..., description="Tenant identifier")
    file_id: str = Field(..., description="File identifier")
    metadata_updates: dict[str, Any] = Field(..., description="Fields to update")


class UpdateMetadataOutput(BaseModel):
    """Output from update metadata use case."""

    file_id: str = Field(..., description="File identifier")
    filename: str = Field(..., description="Original filename")
    updated_at: datetime = Field(..., description="Update timestamp")
    metadata: DocumentMetadata = Field(..., description="Updated metadata")


# Delete Document DTOs
class DeleteDocumentInput(BaseModel):
    """Input for delete document use case."""

    tenant_id: str = Field(..., description="Tenant identifier")
    file_id: str = Field(..., description="File identifier")


class DeleteDocumentOutput(BaseModel):
    """Output from delete document use case."""

    file_id: str = Field(..., description="Deleted file identifier")
    filename: str = Field(..., description="Original filename")
    deleted_at: datetime = Field(..., description="Deletion timestamp")
    message: str = Field(default="Document successfully deleted", description="Confirmation message")


# List Documents DTOs
class ListDocumentsInput(BaseModel):
    """Input for list documents use case."""

    tenant_id: str = Field(..., description="Tenant identifier")
    limit: int = Field(default=20, ge=1, le=100, description="Maximum items per page")
    cursor: str | None = Field(default=None, description="Pagination cursor")

    # Metadata filters (all stored as SQL columns in file_metadata)
    document_type: str | None = Field(default=None, description="Filter by document type")
    tags: list[str] | None = Field(default=None, description="Filter by tags")
    source: str | None = Field(default=None, description="Filter by source")
    department: str | None = Field(default=None, description="Filter by department")

    # Promoted field filters (structured columns in metadata storage)
    operation_number: str | None = Field(default=None, description="Filter by operation number (e.g., UR-P1180)")
    country: str | None = Field(default=None, description="Filter by country")
    sector: str | None = Field(default=None, description="Filter by sector (e.g., TRANSPORT)")
    disclosed: bool | None = Field(default=None, description="Filter by disclosure status")
    year: int | None = Field(default=None, description="Filter by exact year")
    year_min: int | None = Field(default=None, description="Filter by minimum year (inclusive)")
    year_max: int | None = Field(default=None, description="Filter by maximum year (inclusive)")
    operation_type: str | None = Field(default=None, description="Filter by operation type")
    dept_id: str | None = Field(default=None, description="Filter by department ID (e.g., INE/TSP)")
    document_author: str | None = Field(default=None, description="Filter by document author (partial match)")
    file_extension: str | None = Field(default=None, description="Filter by file extension (e.g., .pdf)")
    access_to_information_policy: str | None = Field(default=None, description="Filter by access policy")
    ezshare_id: str | None = Field(default=None, description="Filter by EZSHARE ID")

    # Sorting
    sort_by: str = Field(default="created_at", description="Sort field")
    sort_order: str = Field(default="desc", description="Sort order (asc/desc)")


class ListDocumentsOutput(BaseModel):
    """Output from list documents use case."""

    documents: list[DocumentDTO] = Field(..., description="List of documents")
    pagination: PaginationDTO = Field(..., description="Pagination information")
