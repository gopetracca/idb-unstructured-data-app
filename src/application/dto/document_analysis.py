"""DTOs for document analysis operations."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ProcessingStatus(StrEnum):
    """Status of document analysis processing."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentAnalysisRequest(BaseModel):
    """Request DTO for document analysis."""

    file_id: str = Field(..., description="Unique file identifier")
    tenant_id: str = Field(default="default", description="Tenant identifier")
    source_container: str = Field(default="raw", description="Source blob container")
    output_container: str = Field(default="text", description="Output blob container")
    correlation_id: str | None = Field(
        default=None, description="Optional correlation ID for tracing"
    )


class DocumentAnalysisResult(BaseModel):
    """Result DTO for document analysis."""

    file_id: str = Field(..., description="Unique file identifier")
    status: ProcessingStatus = Field(..., description="Processing status")
    markdown_url: str | None = Field(
        default=None, description="URL to the markdown output blob"
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

