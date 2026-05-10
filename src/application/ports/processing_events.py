"""ProcessingEvents port interface for stage execution tracking."""

from typing import Protocol

from src.core.entities.processing_event import ProcessingEvent, StageDurationStats


class ProcessingEventsPort(Protocol):
    """Port interface for recording and querying processing stage events.

    Implementations track which stage was executed for each file,
    enabling pipeline observability and performance analysis.
    """

    async def log_stage_event(
        self,
        file_id: str,
        tenant_id: str,
        stage: str,
        status: str,
        duration_ms: int | None = None,
        error_message: str | None = None,
        metadata_json: str | None = None,
    ) -> ProcessingEvent:
        """Record a stage execution event.

        Args:
            file_id: File identifier
            tenant_id: Tenant identifier
            stage: Stage being executed (e.g. "convert", "chunk")
            status: Stage status (success, failed, retrying)
            duration_ms: Duration of the stage execution
            error_message: Error details if failed
            metadata_json: Additional context as JSON

        Returns:
            Created ProcessingEvent
        """
        ...

    async def get_file_timeline(
        self, file_id: str, tenant_id: str
    ) -> list[ProcessingEvent]:
        """Get ordered stage event history for a file.

        Args:
            file_id: File identifier
            tenant_id: Tenant identifier (required for tenant isolation)

        Returns:
            List of ProcessingEvent ordered by timestamp ascending
        """
        ...

    async def get_stage_statistics(
        self,
        tenant_id: str,
        stage: str | None = None,
    ) -> list[StageDurationStats]:
        """Get aggregate duration statistics per stage.

        Args:
            tenant_id: Tenant identifier
            stage: Optional stage filter (all stages if None)

        Returns:
            List of StageDurationStats per stage
        """
        ...

    async def get_failed_transitions(
        self,
        tenant_id: str,
        limit: int = 50,
    ) -> list[ProcessingEvent]:
        """Get recent failed stage events for debugging.

        Args:
            tenant_id: Tenant identifier
            limit: Maximum number of results

        Returns:
            List of failed ProcessingEvent ordered by timestamp descending
        """
        ...
