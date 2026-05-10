"""Document metadata models for promoted SQL fields.

These models define the metadata fields stored as dedicated SQL columns
on the file_metadata table (Single Table Inheritance pattern).

The model hierarchy serves as:
- The registry of promoted field names (via promoted_field_names())
- Input validation per document type
- Future type-specific required field enforcement
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class DocumentMetadata(BaseModel):
    """Base promoted metadata fields — shared by ALL document types.

    Every field here maps 1:1 to a nullable column on the file_metadata table.
    Subclass for document-type-specific fields or required field enforcement.
    """

    file_id: str = Field(..., description="File identifier (FK to files)")
    document_type: str | None = Field(default=None, max_length=100)
    language: str | None = Field(default="en", max_length=10)
    country: str | None = Field(default=None, max_length=100)
    year: int | None = Field(default=None, ge=1900, le=2100)
    document_author: str | None = Field(default=None, max_length=200)
    document_name: str | None = Field(default=None, max_length=500)
    document_url: str | None = Field(default=None)
    disclosed: bool | None = Field(default=None)
    file_extension: str | None = Field(default=None, max_length=10)
    access_to_information_policy: str | None = Field(default=None)
    document_publish_date: datetime | None = Field(default=None)
    document_approval_date: datetime | None = Field(default=None)
    document_created_date: datetime | None = Field(default=None)
    # Migrated from FileMetadata
    source: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags(cls, v: Any) -> list[str]:
        """Ensure tags is always a list of strings."""
        if v is None:
            return []
        if isinstance(v, str):
            return [tag.strip() for tag in v.split(",") if tag.strip()]
        if isinstance(v, list):
            return [str(tag).strip() for tag in v if tag]
        return []

    @classmethod
    def promoted_field_names(cls) -> frozenset[str]:
        """Returns the set of promoted metadata field names that map to SQL columns.

        Excludes `file_id` which is an identity key, not a promoted metadata field.
        For subclasses, this includes both base and subclass-specific fields.
        """
        return frozenset(cls.model_fields.keys()) - {"file_id"}

    @classmethod
    def from_source(cls, file_id: str, source: Any) -> "DocumentMetadata":
        """Extract promoted fields from any source object with matching attributes.

        Args:
            file_id: File identifier to associate with this metadata.
            source: Object with attributes matching promoted field names (e.g., a dict or entity).
        """
        data: dict[str, Any] = {"file_id": file_id}
        for field_name in cls.promoted_field_names():
            if isinstance(source, dict):
                value = source.get(field_name)
            else:
                value = getattr(source, field_name, None)
            if value is not None:
                data[field_name] = value
        return cls(**data)

    def to_dict(self, exclude_none: bool = True) -> dict[str, Any]:
        """Convert to dictionary, optionally excluding None values."""
        return self.model_dump(exclude_none=exclude_none)


class OperationalDocumentMetadata(DocumentMetadata):
    """Fields specific to operational documents (loans, grants, TCs)."""

    operation_number: str | None = Field(default=None, max_length=50)
    sector: str | None = Field(default=None, max_length=100)
    operation_type: str | None = Field(default=None, max_length=100)
    dept_id: str | None = Field(default=None, max_length=100)


class PublicationDocumentMetadata(DocumentMetadata):
    """Fields specific to research publications (journals, working papers, etc.).

    Research publications include journal articles, working papers, book chapters,
    conference papers, and other academic/research materials.
    """

    journal: str | None = Field(
        default=None,
        max_length=500,
        description="Journal or publication venue name",
    )
    doi: str | None = Field(
        default=None,
        max_length=200,
        description="Digital Object Identifier",
    )
    issn: str | None = Field(
        default=None,
        max_length=50,
        description="International Standard Serial Number",
    )
    peer_reviewed: bool | None = Field(
        default=None,
        description="Whether the publication was peer-reviewed",
    )
    publication_type: str | None = Field(
        default=None,
        max_length=100,
        description="Type of publication (journal_article, working_paper, book_chapter)",
    )
    publication_date: datetime | None = Field(
        default=None,
        description="Date of publication",
    )


# --- Type Registry ---

METADATA_MODELS: dict[str, type[DocumentMetadata]] = {
    "operational": OperationalDocumentMetadata,
    "publication": PublicationDocumentMetadata,
}


def get_metadata_model(document_type: str | None) -> type[DocumentMetadata]:
    """Get the validation model for a document type.

    Falls back to OperationalDocumentMetadata for unknown/unspecified types
    since all current documents in the system are operational documents.

    Args:
        document_type: The document type string (e.g., "operational", "publication")

    Returns:
        The appropriate DocumentMetadata subclass for the document type
    """
    if not document_type:
        return OperationalDocumentMetadata
    return METADATA_MODELS.get(document_type, DocumentMetadata)


def list_metadata_types() -> list[str]:
    """Return list of registered document metadata types."""
    return sorted(METADATA_MODELS.keys())
