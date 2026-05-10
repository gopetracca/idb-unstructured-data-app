"""SQLAlchemy model for the chunks table."""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.entities.chunk_index import ChunkIndex
from src.infrastructure.sqlserver.models.base import Base


class ChunkTable(Base):
    """ORM model for the `chunks` table.

    Contains only core positional/structural data. Processing metadata
    (embedding_status, metadata_json) lives in ChunkMetadataTable.
    Parent fields (tenant_id, file_version) are derived via the file_id
    FK to the files table.
    """

    __tablename__ = "chunks"

    chunk_id: Mapped[str] = mapped_column(sa.String(200), primary_key=True)
    file_id: Mapped[str] = mapped_column(
        sa.String(36),
        sa.ForeignKey("files.file_id", ondelete="CASCADE"),
        nullable=False,
    )

    # Position
    chunk_index: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    # Content reference
    text_preview: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    start_char: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    end_char: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    page_number: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)

    # Blob storage references (SSOT for content location)
    chunk_blob_ref: Mapped[str | None] = mapped_column(sa.String(1024), nullable=True)
    embedding_blob_ref: Mapped[str | None] = mapped_column(sa.String(1024), nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, server_default=sa.func.now()
    )

    # Relationships
    file: Mapped["FileTable"] = relationship("FileTable", back_populates="chunks")
    metadata_record: Mapped["ChunkMetadataTable"] = relationship(
        "ChunkMetadataTable",
        back_populates="chunk",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="joined",
    )
    vector_refs: Mapped[list["ChunkVectorRefTable"]] = relationship(
        "ChunkVectorRefTable",
        back_populates="chunk",
        cascade="all, delete-orphan",
        lazy="select",
    )

    # Indexes and constraints
    __table_args__ = (
        sa.UniqueConstraint(
            "file_id", "chunk_index",
            name="ux_chunks_file_index",
        ),
    )

    def to_entity(self) -> ChunkIndex:
        """Convert ORM model to core ChunkIndex entity."""
        return ChunkIndex(
            file_id=self.file_id,
            chunk_id=self.chunk_id,
            chunk_index=self.chunk_index,
            text_preview=self.text_preview or "",
            start_char=self.start_char,
            end_char=self.end_char,
            page_number=self.page_number,
            # Blob storage references
            chunk_blob_ref=self.chunk_blob_ref,
            embedding_blob_ref=self.embedding_blob_ref,
            created_timestamp=self.created_at,
        )

    @classmethod
    def from_entity(cls, entity: ChunkIndex) -> "ChunkTable":
        """Create ORM model from core ChunkIndex entity."""
        return cls(
            chunk_id=entity.chunk_id,
            file_id=entity.file_id,
            chunk_index=entity.chunk_index,
            text_preview=entity.text_preview[:500] if entity.text_preview else None,
            start_char=entity.start_char,
            end_char=entity.end_char,
            page_number=entity.page_number,
            # Blob storage references
            chunk_blob_ref=entity.chunk_blob_ref,
            embedding_blob_ref=entity.embedding_blob_ref,
            created_at=entity.created_timestamp,
        )

    def update_from_entity(self, entity: ChunkIndex) -> None:
        """Update ORM model fields from a ChunkIndex entity."""
        self.text_preview = entity.text_preview[:500] if entity.text_preview else None


from src.infrastructure.sqlserver.models.chunk_metadata_model import ChunkMetadataTable  # noqa: E402
from src.infrastructure.sqlserver.models.chunk_vector_ref_model import ChunkVectorRefTable  # noqa: E402
from src.infrastructure.sqlserver.models.file_model import FileTable  # noqa: E402
