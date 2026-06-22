"""Pydantic schemas for document API endpoints."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MetadataSchema(BaseModel):
    """Schema for document metadata in API responses.

    Combines flexible JSON fields with promoted SQL fields for a unified view.
    """

    # Flexible fields (from files.metadata_json)
    tags: list[str] = Field(
        default_factory=list,
        description="List of tags for categorization",
        examples=[["annual-report", "2024", "operations"]],
    )
    source: str | None = Field(
        None,
        description="Source system or origin of the document",
        examples=["ezshare", "sharepoint", "manual-upload"],
    )
    author: str | None = Field(
        None,
        description="Document author name",
        examples=["John Smith"],
    )
    department: str | None = Field(
        None,
        description="Department that owns the document",
        examples=["Operations", "Finance", "Legal"],
    )
    description: str | None = Field(
        None,
        description="Brief description of the document content",
        examples=["Q4 2024 Financial Report for Operations Division"],
    )

    # Promoted fields (from file_metadata SQL columns)
    document_category: str | None = Field(
        None,
        description="Schema discriminator: 'operational' or 'publication'",
        examples=["operational", "publication"],
    )
    document_type: str | None = Field(
        None,
        description="User-facing document classification (e.g., PCR, Report, LP)",
        examples=["PCR", "Report", "LP", "MIC"],
    )
    language: str | None = Field(
        default="en",
        description="ISO 639-1 language code",
        examples=["en", "es", "fr"],
    )
    operation_number: str | None = Field(None, description="Operation number (e.g., UR-P1180)")
    country: str | None = Field(None, description="Country")
    sector: str | None = Field(None, description="Sector classification")
    year: int | None = Field(None, description="Publication year")
    operation_type: str | None = Field(None, description="Operation type")
    dept_id: str | None = Field(None, description="Department ID")
    document_author: str | None = Field(None, description="Primary document author")
    document_name: str | None = Field(None, description="Document display name")
    document_url: str | None = Field(None, description="URL of the document")
    disclosed: bool | None = Field(None, description="Disclosure status")
    file_extension: str | None = Field(None, description="File extension (e.g., .pdf)")
    access_to_information_policy: str | None = Field(None, description="Access policy")
    document_publish_date: datetime | None = Field(None, description="Publication date")
    document_approval_date: datetime | None = Field(None, description="Approval date")
    document_created_date: datetime | None = Field(None, description="Created date")

    model_config = {"extra": "allow"}


class UploadDocumentResponse(BaseModel):
    """Response schema for document upload endpoint."""

    file_id: str = Field(..., description="Unique file identifier")
    filename: str = Field(..., description="Original filename")
    size_bytes: int = Field(..., description="File size in bytes")
    mime_type: str = Field(..., description="MIME type")
    uploaded_at: datetime = Field(..., description="Upload timestamp")
    metadata: MetadataSchema = Field(..., description="Document metadata")

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


class UpdateMetadataRequest(BaseModel):
    """Request schema for metadata update endpoint.

    Supports updating both flexible (JSON) and promoted (SQL) fields.
    """

    # Flexible metadata (stored in JSON)
    tags: list[str] | None = Field(None, description="Tags for categorization")
    source: str | None = Field(None, description="Document source")
    author: str | None = Field(None, description="Document author")
    department: str | None = Field(None, description="Organizational department")
    description: str | None = Field(None, description="Document description")

    # Promoted fields (stored in SQL columns)
    document_category: str | None = Field(None, description="Schema discriminator (operational, publication)")
    document_type: str | None = Field(None, description="User-facing document classification (e.g., PCR, Report)")
    language: str | None = Field(None, description="ISO 639-1 language code")
    operation_number: str | None = Field(None, description="Operation number")
    country: str | None = Field(None, description="Country")
    sector: str | None = Field(None, description="Sector classification")
    year: int | None = Field(None, description="Publication year")
    operation_type: str | None = Field(None, description="Operation type")
    dept_id: str | None = Field(None, description="Department ID")
    document_author: str | None = Field(None, description="Primary document author")
    document_name: str | None = Field(None, description="Document display name")
    document_url: str | None = Field(None, description="Document URL")
    disclosed: bool | None = Field(None, description="Disclosure status")
    file_extension: str | None = Field(None, description="File extension")
    access_to_information_policy: str | None = Field(None, description="Access policy")
    document_publish_date: datetime | None = Field(None, description="Publication date")
    document_approval_date: datetime | None = Field(None, description="Approval date")
    document_created_date: datetime | None = Field(None, description="Created date")

    def to_update_dict(self) -> dict[str, Any]:
        """Convert to dictionary with only non-None values."""
        return {k: v for k, v in self.model_dump().items() if v is not None}


class UpdateMetadataResponse(BaseModel):
    """Response schema for metadata update endpoint."""

    file_id: str = Field(..., description="File identifier")
    filename: str = Field(..., description="Original filename")
    updated_at: datetime = Field(..., description="Update timestamp")
    metadata: MetadataSchema = Field(..., description="Updated metadata")

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


class DeleteDocumentResponse(BaseModel):
    """Response schema for document deletion endpoint."""

    file_id: str = Field(..., description="Deleted file identifier")
    filename: str = Field(..., description="Original filename")
    deleted_at: datetime = Field(..., description="Deletion timestamp")
    message: str = Field(default="Document successfully deleted", description="Confirmation")

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


class DocumentSchema(BaseModel):
    """Schema for a single document in list responses."""

    file_id: str = Field(..., description="Unique file identifier")
    filename: str = Field(..., description="Original filename")
    size_bytes: int = Field(..., description="File size in bytes")
    mime_type: str = Field(..., description="MIME type")
    created_at: datetime = Field(..., description="Upload timestamp")
    updated_at: datetime = Field(..., description="Last modification timestamp")
    metadata: MetadataSchema = Field(..., description="Document metadata")

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


class PaginationSchema(BaseModel):
    """Schema for pagination information."""

    total_count: int = Field(..., ge=0, description="Total number of items")
    limit: int = Field(..., ge=1, description="Items per page")
    has_next: bool = Field(..., description="Whether there are more items")
    has_previous: bool = Field(..., description="Whether there are previous items")
    next_cursor: str | None = Field(None, description="Cursor for next page")
    previous_cursor: str | None = Field(None, description="Cursor for previous page")


class ListDocumentsResponse(BaseModel):
    """Response schema for document listing endpoint."""

    documents: list[DocumentSchema] = Field(..., description="List of documents")
    pagination: PaginationSchema = Field(..., description="Pagination information")


class ErrorResponse(BaseModel):
    """Standard error response schema."""

    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: dict[str, Any] | None = Field(None, description="Additional error details")
