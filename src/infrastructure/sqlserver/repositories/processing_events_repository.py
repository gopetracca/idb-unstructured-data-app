"""SQL Server repository for processing events (stage execution tracking)."""

import logging
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.entities.processing_event import ProcessingEvent, StageDurationStats
from src.infrastructure.sqlserver.models.processing_event_model import ProcessingEventTable

logger = logging.getLogger(__name__)


class ProcessingEventsRepositorySQLServer:
    """Repository for recording and querying processing stage events.

    Implements the ProcessingEventsPort interface backed by the
    `processing_events` table in SQL Server.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

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

        If duration_ms is not provided, it is calculated from the previous
        event for the same file.
        """
        async with self._session_factory() as session:
            if duration_ms is None:
                duration_ms = await self._calculate_duration(session, file_id)

            row = ProcessingEventTable(
                file_id=file_id,
                tenant_id=tenant_id,
                stage=stage,
                status=status,
                event_timestamp=datetime.utcnow(),
                duration_ms=duration_ms,
                error_message=error_message,
                metadata_json=metadata_json,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)

            return row.to_entity()

    async def _calculate_duration(
        self, session: AsyncSession, file_id: str
    ) -> int | None:
        """Calculate duration since the previous event for this file."""
        stmt = (
            sa.select(ProcessingEventTable.event_timestamp)
            .where(ProcessingEventTable.file_id == file_id)
            .order_by(ProcessingEventTable.event_timestamp.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        prev_timestamp = result.scalar_one_or_none()
        if prev_timestamp is None:
            return None

        delta = datetime.utcnow() - prev_timestamp
        return int(delta.total_seconds() * 1000)

    async def get_file_timeline(
        self, file_id: str, tenant_id: str
    ) -> list[ProcessingEvent]:
        """Get ordered stage event history for a file."""
        async with self._session_factory() as session:
            stmt = (
                sa.select(ProcessingEventTable)
                .where(
                    ProcessingEventTable.file_id == file_id,
                    ProcessingEventTable.tenant_id == tenant_id,
                )
                .order_by(ProcessingEventTable.event_timestamp.asc(), ProcessingEventTable.event_id.asc())
            )
            result = await session.execute(stmt)
            return [row.to_entity() for row in result.scalars().all()]

    async def get_stage_statistics(
        self,
        tenant_id: str,
        stage: str | None = None,
    ) -> list[StageDurationStats]:
        """Get aggregate duration statistics per stage."""
        async with self._session_factory() as session:
            stmt = (
                sa.select(
                    ProcessingEventTable.stage,
                    sa.func.avg(ProcessingEventTable.duration_ms).label("avg_duration_ms"),
                    sa.func.min(ProcessingEventTable.duration_ms).label("min_duration_ms"),
                    sa.func.max(ProcessingEventTable.duration_ms).label("max_duration_ms"),
                    sa.func.count().label("sample_count"),
                )
                .where(
                    ProcessingEventTable.tenant_id == tenant_id,
                    ProcessingEventTable.status == "success",
                    ProcessingEventTable.duration_ms.isnot(None),
                )
                .group_by(ProcessingEventTable.stage)
                .order_by(sa.desc("avg_duration_ms"))
            )

            if stage:
                stmt = stmt.where(ProcessingEventTable.stage == stage)

            result = await session.execute(stmt)
            return [
                StageDurationStats(
                    stage=row.stage,
                    avg_duration_ms=float(row.avg_duration_ms),
                    min_duration_ms=int(row.min_duration_ms),
                    max_duration_ms=int(row.max_duration_ms),
                    sample_count=row.sample_count,
                )
                for row in result.all()
            ]

    async def get_failed_transitions(
        self,
        tenant_id: str,
        limit: int = 50,
    ) -> list[ProcessingEvent]:
        """Get recent failed stage events for debugging."""
        async with self._session_factory() as session:
            stmt = (
                sa.select(ProcessingEventTable)
                .where(
                    ProcessingEventTable.tenant_id == tenant_id,
                    ProcessingEventTable.status == "failed",
                )
                .order_by(ProcessingEventTable.event_timestamp.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [row.to_entity() for row in result.scalars().all()]
