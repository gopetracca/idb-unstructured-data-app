"""Analytics API routes for processing pipeline observability."""

from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query, Security, status

from src.container import Container
from src.presentation.http.auth import CurrentUser, get_current_user
from src.presentation.http.tenant import TenantId
from src.presentation.http.schemas.analytics import (
    ProcessingTimelineResponse,
    StageDurationStatisticsResponse,
    StageDurationStatSchema,
    StageEventSchema,
)

router = APIRouter(prefix="/api/v1", tags=["analytics"])


@router.get(
    "/documents/{file_id}/processing-timeline",
    response_model=ProcessingTimelineResponse,
    summary="Get processing timeline",
    description="Get the ordered stage transition history for a document.",
)
@inject
async def get_processing_timeline(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=["api.read"])],
    file_id: str,
    tenant_id: TenantId,
    processing_events_repository=Depends(Provide[Container.processing_events_repository]),
) -> ProcessingTimelineResponse:
    """Get the processing timeline for a specific document."""
    if processing_events_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "FeatureDisabled",
                "message": "Processing analytics requires SQL Server to be enabled",
            },
        )

    events = await processing_events_repository.get_file_timeline(
        file_id, tenant_id=tenant_id
    )

    # Calculate total duration from first to last event
    total_duration_ms = None
    if len(events) >= 2:
        first = events[0].event_timestamp
        last = events[-1].event_timestamp
        total_duration_ms = int((last - first).total_seconds() * 1000)

    return ProcessingTimelineResponse(
        file_id=file_id,
        events=[
            StageEventSchema(
                event_id=e.event_id,
                stage=e.stage,
                status=e.status,
                event_timestamp=e.event_timestamp,
                duration_ms=e.duration_ms,
                error_message=e.error_message,
            )
            for e in events
        ],
        total_duration_ms=total_duration_ms,
    )


@router.get(
    "/analytics/stage-durations",
    response_model=StageDurationStatisticsResponse,
    summary="Get stage duration statistics",
    description="Get aggregate processing duration statistics per stage.",
)
@inject
async def get_stage_duration_statistics(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=["api.read"])],
    tenant_id: TenantId,
    stage: Annotated[
        str | None,
        Query(description="Optional stage filter"),
    ] = None,
    processing_events_repository=Depends(Provide[Container.processing_events_repository]),
) -> StageDurationStatisticsResponse:
    """Get aggregate stage duration statistics for a tenant."""
    if processing_events_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "FeatureDisabled",
                "message": "Processing analytics requires SQL Server to be enabled",
            },
        )

    stats = await processing_events_repository.get_stage_statistics(
        tenant_id=tenant_id,
        stage=stage,
    )

    return StageDurationStatisticsResponse(
        tenant_id=tenant_id,
        stages=[
            StageDurationStatSchema(
                stage=s.stage,
                avg_duration_ms=s.avg_duration_ms,
                min_duration_ms=s.min_duration_ms,
                max_duration_ms=s.max_duration_ms,
                sample_count=s.sample_count,
            )
            for s in stats
        ],
    )
