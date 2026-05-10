"""ProcessingEvent entity for stage execution tracking."""

from datetime import datetime

from pydantic import BaseModel, Field


class ProcessingEvent(BaseModel):
    """Represents a processing stage event for a file in the pipeline.

    Each event records which stage was executed, along with timing
    and status information.
    """

    event_id: int | None = Field(default=None, description="Auto-generated event ID")
    file_id: str = Field(..., description="File identifier")
    tenant_id: str = Field(..., description="Tenant identifier")

    # Stage information
    stage: str = Field(..., description="Processing stage being executed")
    status: str = Field(..., description="Stage status (success, failed, retrying)")

    # Timing
    event_timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When the transition occurred"
    )
    duration_ms: int | None = Field(
        default=None, description="Duration since previous stage transition (ms)"
    )

    # Additional context
    error_message: str | None = Field(default=None, description="Error details if failed")
    metadata_json: str | None = Field(
        default=None, description="Additional context as JSON"
    )


class StageDurationStats(BaseModel):
    """Aggregate statistics for processing duration of a specific stage."""

    stage: str = Field(..., description="Processing stage name")
    avg_duration_ms: float = Field(..., description="Average duration in milliseconds")
    min_duration_ms: int = Field(..., description="Minimum duration in milliseconds")
    max_duration_ms: int = Field(..., description="Maximum duration in milliseconds")
    sample_count: int = Field(..., description="Number of samples")
