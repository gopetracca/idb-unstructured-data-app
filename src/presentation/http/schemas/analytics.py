"""Schemas for processing analytics endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field


class StageEventSchema(BaseModel):
    """A single processing stage execution event."""

    event_id: int | None = Field(default=None, description="Event identifier")
    stage: str = Field(..., description="Stage being executed")
    status: str = Field(..., description="Stage status")
    event_timestamp: datetime = Field(..., description="When the stage was executed")
    duration_ms: int | None = Field(default=None, description="Duration of the stage (ms)")
    error_message: str | None = Field(default=None, description="Error details if failed")


class ProcessingTimelineResponse(BaseModel):
    """Response for document processing timeline."""

    file_id: str = Field(..., description="File identifier")
    events: list[StageEventSchema] = Field(
        default_factory=list, description="Ordered list of stage events"
    )
    total_duration_ms: int | None = Field(
        default=None, description="Total processing duration (ms)"
    )


class StageDurationStatSchema(BaseModel):
    """Aggregate duration statistics for a processing stage."""

    stage: str = Field(..., description="Processing stage name")
    avg_duration_ms: float = Field(..., description="Average duration (ms)")
    min_duration_ms: int = Field(..., description="Minimum duration (ms)")
    max_duration_ms: int = Field(..., description="Maximum duration (ms)")
    sample_count: int = Field(..., description="Number of samples")


class StageDurationStatisticsResponse(BaseModel):
    """Response for stage duration statistics."""

    tenant_id: str = Field(..., description="Tenant identifier")
    stages: list[StageDurationStatSchema] = Field(
        default_factory=list, description="Duration statistics per stage"
    )
