"""SQLAlchemy model for the processing_events table."""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.entities.processing_event import ProcessingEvent
from src.infrastructure.sqlserver.models.base import Base


class ProcessingEventTable(Base):
    """ORM model for the `processing_events` table.

    Records stage execution events with timestamps for pipeline observability.
    """

    __tablename__ = "processing_events"

    event_id: Mapped[int] = mapped_column(
        sa.BigInteger, primary_key=True, autoincrement=True
    )
    file_id: Mapped[str] = mapped_column(
        sa.String(36),
        sa.ForeignKey("files.file_id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)

    # Stage information
    stage: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False)

    # Timing
    event_timestamp: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, server_default=sa.func.now()
    )
    duration_ms: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)

    # Additional context
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    # Relationship
    file: Mapped["FileTable"] = relationship(
        "FileTable", back_populates="processing_events"
    )

    # Indexes
    __table_args__ = (
        sa.Index("ix_events_file_timestamp", "file_id", event_timestamp.desc()),
        sa.Index("ix_events_tenant_stage", "tenant_id", "stage", event_timestamp.desc()),
    )

    def to_entity(self) -> ProcessingEvent:
        """Convert ORM model to core ProcessingEvent entity."""
        return ProcessingEvent.model_validate(self, from_attributes=True)


from src.infrastructure.sqlserver.models.file_model import FileTable  # noqa: E402
