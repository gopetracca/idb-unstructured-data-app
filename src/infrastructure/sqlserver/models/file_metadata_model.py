"""SQLAlchemy model for the file_metadata table."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.value_objects.document_metadata import DocumentMetadata, get_metadata_model
from src.infrastructure.sqlserver.models.base import Base

if TYPE_CHECKING:
    from src.core.entities.file_index import FileIndex


class FileMetadataTable(Base):
    """ORM model for the `file_metadata` table.

    Stores promoted document metadata columns for efficient SQL filtering.
    Uses Single Table Inheritance with document_type as discriminator.
    """

    __tablename__ = "file_metadata"

    file_id: Mapped[str] = mapped_column(
        sa.String(36),
        sa.ForeignKey("files.file_id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Schema discriminator — picks metadata model (operational, publication)
    document_category: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    # User-facing document classification (e.g., PCR, Report, LP, journal_article)
    document_type: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    language: Mapped[str | None] = mapped_column(
        sa.String(10), nullable=True, server_default="en"
    )

    # Promoted columns for filtering
    country: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    sector: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    operation_number: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    operation_type: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    dept_id: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    document_author: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    document_name: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    document_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    file_extension: Mapped[str | None] = mapped_column(sa.String(10), nullable=True)
    disclosed: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    access_to_information_policy: Mapped[str | None] = mapped_column(
        sa.String(50), nullable=True
    )
    document_publish_date: Mapped[datetime | None] = mapped_column(
        sa.DateTime, nullable=True
    )
    document_created_date: Mapped[datetime | None] = mapped_column(
        sa.DateTime, nullable=True
    )
    document_approval_date: Mapped[datetime | None] = mapped_column(
        sa.DateTime, nullable=True
    )
    # Migrated from files.metadata_json
    source: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    department: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    tags: Mapped[list | None] = mapped_column(sa.JSON, nullable=True)

    # Publication-specific columns (Single Table Inheritance)
    journal: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    doi: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    issn: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    peer_reviewed: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    publication_type: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    publication_date: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)

    # Relationship
    file: Mapped["FileTable"] = relationship(
        "FileTable", back_populates="metadata_record"
    )

    # Indexes
    __table_args__ = (
        # Operational document indexes
        sa.Index("ix_metadata_country_sector_year", "country", "sector", "year"),
        sa.Index("ix_metadata_operation_number", "operation_number"),
        sa.Index("ix_metadata_dept_id", "dept_id"),
        sa.Index("ix_metadata_document_author", "document_author"),
        sa.Index("ix_metadata_document_type", "document_type"),
        sa.Index("ix_metadata_document_category", "document_category"),
        # Publication document indexes
        sa.Index("ix_metadata_doi", "doi"),
        sa.Index("ix_metadata_journal", "journal"),
        sa.Index("ix_metadata_peer_reviewed", "peer_reviewed"),
    )

    # Fields excluded from update_from_entity (immutable identity)
    _UPDATE_EXCLUDE = frozenset({"file_id"})

    def to_entity(self) -> DocumentMetadata:
        """Convert ORM model to the appropriate DocumentMetadata subclass.

        Uses get_metadata_model() to select the correct Pydantic model
        based on document_category, so operational/publication fields are preserved.
        """
        model_cls = get_metadata_model(self.document_category)
        return model_cls.model_validate(self, from_attributes=True)

    @classmethod
    def from_entity(cls, entity: DocumentMetadata) -> "FileMetadataTable":
        """Create metadata record from a DocumentMetadata entity.

        Handles both base DocumentMetadata and subclasses like
        OperationalDocumentMetadata via model_dump which includes all fields.
        """
        return cls(**entity.model_dump())

    def update_from_entity(self, entity: DocumentMetadata) -> None:
        """Update metadata fields from a DocumentMetadata entity.

        Uses model_dump to get all fields, then defaults missing subclass
        fields (e.g. sector, operation_number) to None so they are cleared
        when the entity type narrows.
        """
        data = entity.model_dump(exclude=self._UPDATE_EXCLUDE)
        for col in self.__table__.columns.keys():
            if col in self._UPDATE_EXCLUDE:
                continue
            setattr(self, col, data.get(col))

    @classmethod
    def from_file_index(cls, fi: "FileIndex") -> "FileMetadataTable":
        """Create a FileMetadataTable row from the metadata portion of a FileIndex."""
        cols = {c for c in cls.__table__.columns.keys()}
        data = fi.model_dump(include=cols)
        return cls(**data)

    def update_from_file_index(self, fi: "FileIndex") -> None:
        """Update metadata columns from a FileIndex entity."""
        fi_data = fi.model_dump()
        for col in self.__table__.columns.keys():
            if col in self._UPDATE_EXCLUDE:
                continue
            if col in fi_data:
                setattr(self, col, fi_data[col])


# Forward reference
from src.infrastructure.sqlserver.models.file_model import FileTable  # noqa: E402
