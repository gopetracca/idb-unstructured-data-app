"""SQLAlchemy model for the files table."""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.entities.document import Document
from src.infrastructure.sqlserver.models.base import Base


class FileTable(Base):
    """ORM model for the `files` table.

    Maps to the core Document entity. The `files` table uses SQL Server
    temporal tables (SYSTEM_VERSIONING) for automatic audit history.

    Processing state columns live in the `pipeline_state` table.
    Promoted metadata columns live in the `file_metadata` table.
    """

    __tablename__ = "files"

    # Identity
    file_id: Mapped[str] = mapped_column(
        sa.String(36), primary_key=True, comment="UUID primary key"
    )
    tenant_id: Mapped[str] = mapped_column(
        sa.String(64), nullable=False, index=True
    )

    # External IDs
    ezshare_id: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)

    # File attributes
    blob_name: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(
        sa.String(128), nullable=False, server_default="application/octet-stream"
    )
    size_bytes: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, server_default="0")
    content_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False, server_default="")
    file_version: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="1")

    # Blob storage references (SSOT for content location)
    raw_blob_ref: Mapped[str | None] = mapped_column(sa.String(1024), nullable=True)
    text_blob_ref: Mapped[str | None] = mapped_column(sa.String(1024), nullable=True)

    # Collection reference
    collection_name: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)

    # Audit timestamps
    upload_timestamp: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, server_default=sa.func.now()
    )
    last_updated: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()
    )
    created_by: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)

    # Relationships
    metadata_record: Mapped["FileMetadataTable"] = relationship(
        "FileMetadataTable",
        back_populates="file",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="joined",
    )
    pipeline_state: Mapped["PipelineStateTable"] = relationship(
        "PipelineStateTable",
        back_populates="file",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="joined",
    )
    chunks: Mapped[list["ChunkTable"]] = relationship(
        "ChunkTable",
        back_populates="file",
        cascade="all, delete-orphan",
        lazy="select",
    )
    processing_events: Mapped[list["ProcessingEventTable"]] = relationship(
        "ProcessingEventTable",
        back_populates="file",
        cascade="all, delete-orphan",
        lazy="select",
    )

    # Indexes
    __table_args__ = (
        sa.Index("ix_files_content_hash", "content_hash"),
        sa.Index(
            "ux_files_tenant_ezshare",
            "tenant_id",
            "ezshare_id",
            unique=True,
            mssql_where=sa.text("ezshare_id IS NOT NULL"),
        ),
    )

    # Fields excluded from update_from_entity (immutable identity)
    _UPDATE_EXCLUDE = frozenset({"file_id", "upload_timestamp"})

    # Columns owned by this table (used for FileIndex split/assemble)
    _FILE_TABLE_FIELDS = frozenset({
        "file_id", "tenant_id", "blob_name", "content_type", "size_bytes",
        "content_hash", "file_version", "raw_blob_ref", "text_blob_ref",
        "collection_name", "ezshare_id",
        "upload_timestamp", "last_updated",
    })

    def to_entity(self) -> Document:
        """Convert ORM model to core Document entity."""
        return Document.model_validate(self, from_attributes=True)

    @classmethod
    def from_entity(cls, entity: Document) -> "FileTable":
        """Create ORM model from core Document entity."""
        return cls(**entity.model_dump())

    def update_from_entity(self, entity: Document) -> None:
        """Update ORM model fields from a Document entity."""
        for field, value in entity.model_dump(exclude=self._UPDATE_EXCLUDE).items():
            setattr(self, field, value)

    @classmethod
    def from_file_index(cls, fi: "FileIndex") -> "FileTable":
        """Create a FileTable row from a flat FileIndex entity."""
        data = fi.model_dump(include=cls._FILE_TABLE_FIELDS)
        return cls(**data)

    def update_from_file_index(self, fi: "FileIndex") -> None:
        """Update FileTable columns from a FileIndex entity."""
        exclude = self._UPDATE_EXCLUDE | (self._FILE_TABLE_FIELDS - self._FILE_TABLE_FIELDS)
        data = fi.model_dump(include=self._FILE_TABLE_FIELDS, exclude=self._UPDATE_EXCLUDE)
        for field, value in data.items():
            setattr(self, field, value)

    def to_file_index(self) -> "FileIndex":
        """Assemble a flat FileIndex from this row and its joined relations."""
        from src.core.entities.file_index import FileIndex

        file_data = {col: getattr(self, col) for col in self._FILE_TABLE_FIELDS}

        ps = self.pipeline_state
        if ps is not None:
            file_data.update({
                "current_stage": ps.current_stage,
                "overall_status": ps.overall_status,
                "chunk_count": ps.chunk_count,
                "embedded_chunk_count": ps.embedded_chunk_count,
                "chunking_strategy": ps.chunking_strategy,
                "embedding_model": ps.embedding_model,
                "vector_db_targets": ps.vector_db_targets,
                "error_message": ps.error_message,
                "retry_count": ps.retry_count,
            })

        md = self.metadata_record
        if md is not None:
            for col in md.__table__.columns.keys():
                if col != "file_id":
                    file_data[col] = getattr(md, col)

        return FileIndex.model_validate(file_data)


# Forward references for relationships
from src.infrastructure.sqlserver.models.chunk_model import ChunkTable  # noqa: E402
from src.infrastructure.sqlserver.models.file_metadata_model import FileMetadataTable  # noqa: E402
from src.infrastructure.sqlserver.models.pipeline_state_model import PipelineStateTable  # noqa: E402
from src.infrastructure.sqlserver.models.processing_event_model import ProcessingEventTable  # noqa: E402
