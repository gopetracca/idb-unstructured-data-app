"""HTTP schemas for document analysis endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field


class DocumentAnalysisRequestSchema(BaseModel):
    """Request schema for document analysis endpoint."""

    file_id: str = Field(..., description="Unique file identifier (UUID)")
    # tenant_id is resolved server-side (issue #143); not accepted from the client.
    source_container: str = Field(
        default="raw",
        description="Source blob container name",
    )
    output_container: str = Field(
        default="text",
        description="Output blob container name",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "file_id": "550e8400-e29b-41d4-a716-446655440000",
                    "source_container": "raw",
                    "output_container": "text",
                }
            ]
        }
    }


class DocumentAnalysisResponseSchema(BaseModel):
    """Response schema for document analysis endpoint."""

    file_id: str = Field(..., description="Unique file identifier")
    status: str = Field(..., description="Processing status")
    markdown_url: str | None = Field(
        default=None,
        description="URL to the markdown output blob",
    )
    correlation_id: str = Field(..., description="Correlation ID for tracing")
    processing_time_ms: int | None = Field(
        default=None,
        description="Processing time in milliseconds",
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
                    "markdown_url": "text/550e8400-e29b-41d4-a716-446655440000/text.json",
                    "correlation_id": "abc-123-def",
                    "processing_time_ms": 1500,
                    "created_at": "2026-01-27T10:00:00Z",
                }
            ]
        }
    }


class ErrorResponseSchema(BaseModel):
    """Error response schema."""

    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: dict | None = Field(default=None, description="Additional error details")
    correlation_id: str | None = Field(
        default=None,
        description="Correlation ID for tracing",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "error": "DocumentNotFoundError",
                    "message": "Document not found: 550e8400-e29b-41d4-a716-446655440000",
                    "details": {"container": "raw"},
                    "correlation_id": "abc-123-def",
                }
            ]
        }
    }
