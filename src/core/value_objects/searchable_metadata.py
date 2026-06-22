"""SearchableMetadata value object hierarchy.

Fields stored in the vector index per chunk, used for filtering during semantic
search. Assembled at ingestion time from DocumentMetadata + chunk-level data.

This is the typed boundary between the vector database and the rest of the
system — replaces the raw dict[str, Any] that VectorDocument and SearchResult
previously carried.

The hierarchy follows the document type structure:
- BaseSearchableMetadata: Common + chunk fields (all document types)
- OperationalSearchableMetadata: Base + operational-specific fields
- PublicationSearchableMetadata: Base + publication-specific fields
"""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator


class BaseSearchableMetadata(BaseModel):
    """Base metadata stored in the vector index for each chunk.

    Contains common fields (applicable to all document types) and chunk-level
    fields (from the ingestion pipeline). Subclass for document-type-specific
    fields.
    """

    # --- Common document-level fields ---
    document_type: str | None = Field(default=None)
    country: str | None = Field(default=None)
    year: int | None = Field(default=None)
    language: str | None = Field(default=None)
    disclosed: bool | None = Field(default=None)
    ezshare_id: str | None = Field(default=None)
    collection_name: str | None = Field(default=None)
    tags: list[str] = Field(default_factory=list)
    department: str | None = Field(default=None)
    source: str | None = Field(default=None)
    document_name: str | None = Field(default=None)
    document_author: str | None = Field(default=None)
    file_extension: str | None = Field(default=None)
    blob_name: str | None = Field(default=None)

    # --- Chunk-level fields ---
    page_number: int | None = Field(default=None)
    section_path: str | None = Field(default=None)
    has_table: bool | None = Field(default=None)
    table_id: str | None = Field(default=None)

    # --- Chunk processing metadata ---
    model_version: str | None = Field(default=None)
    token_count: int | None = Field(default=None)
    chunking_strategy: str | None = Field(default=None)
    chunk_size: int | None = Field(default=None)
    overlap_chars: int | None = Field(default=None)

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [tag.strip() for tag in v.split(",") if tag.strip()]
        if isinstance(v, list):
            return [str(tag).strip() for tag in v if tag]
        return []

    @field_validator("section_path", mode="before")
    @classmethod
    def coerce_section_path(cls, v: Any) -> str | None:
        """Coerce list[str] heading hierarchy to a joined string.

        ChunkMetadata stores section_path as list[str] (e.g. ['Intro', 'Background']).
        The search index field is a plain string — join with ' > ' separator.
        """
        if isinstance(v, list):
            return " > ".join(v) if v else None
        return v


class OperationalSearchableMetadata(BaseSearchableMetadata):
    """Searchable metadata for operational documents.

    Adds operational-specific fields like operation_number, sector, etc.
    """

    document_type: str | None = Field(default=None)

    # --- Operational-specific fields ---
    operation_number: str | None = Field(default=None)
    sector: str | None = Field(default=None)
    operation_type: str | None = Field(default=None)
    dept_id: str | None = Field(default=None)
    access_to_information_policy: str | None = Field(default=None)
    document_publish_date: str | None = Field(
        default=None, description="ISO date string"
    )
    document_approval_date: str | None = Field(
        default=None, description="ISO date string"
    )


class PublicationSearchableMetadata(BaseSearchableMetadata):
    """Searchable metadata for research publications.

    Adds publication-specific fields like journal, doi, etc.
    """

    document_type: str | None = Field(default=None)

    # --- Publication-specific fields ---
    journal: str | None = Field(default=None)
    doi: str | None = Field(default=None)
    issn: str | None = Field(default=None)
    peer_reviewed: bool | None = Field(default=None)
    publication_type: str | None = Field(default=None)
    publication_date: str | None = Field(default=None, description="ISO date string")


# Type alias for backward compatibility
# Code that uses SearchableMetadata will continue to work
SearchableMetadata = OperationalSearchableMetadata

# Registry mapping document_type -> SearchableMetadata subclass
SEARCHABLE_METADATA_MODELS: dict[str, type[BaseSearchableMetadata]] = {
    "operational": OperationalSearchableMetadata,
    "publication": PublicationSearchableMetadata,
}


def get_searchable_metadata_model(
    document_category: str | None,
) -> type[BaseSearchableMetadata]:
    """Get the SearchableMetadata subclass for a document category.

    Args:
        document_category: Document category string (e.g., "operational", "publication")

    Returns:
        The appropriate SearchableMetadata subclass.
        Defaults to OperationalSearchableMetadata for unknown/None categories.
    """
    if not document_category:
        return OperationalSearchableMetadata
    return SEARCHABLE_METADATA_MODELS.get(document_category, OperationalSearchableMetadata)


def create_searchable_metadata(
    doc_metadata: Any,
    chunk_metadata: dict[str, Any],
    ezshare_id: str | None = None,
    collection_name: str | None = None,
    blob_name: str | None = None,
) -> BaseSearchableMetadata:
    """Factory function to create the appropriate SearchableMetadata subclass.

    Determines the document type from doc_metadata and creates the correct
    subclass with document-level and chunk-level fields populated.

    Args:
        doc_metadata: A DocumentMetadata instance (or subclass).
        chunk_metadata: Raw dict of chunk-level fields from ingestion pipeline.
        ezshare_id: External share ID from the Document entity.
        collection_name: Vector index collection name.
        blob_name: Original filename from the Document entity.

    Returns:
        The appropriate SearchableMetadata subclass instance.
    """
    document_category = getattr(doc_metadata, "document_category", None)
    model_class = get_searchable_metadata_model(document_category)

    # Build common kwargs
    kwargs = _build_common_kwargs(
        doc_metadata, chunk_metadata, ezshare_id, collection_name, blob_name
    )

    # Add type-specific kwargs
    if model_class is OperationalSearchableMetadata:
        kwargs.update(_build_operational_kwargs(doc_metadata))
    elif model_class is PublicationSearchableMetadata:
        kwargs.update(_build_publication_kwargs(doc_metadata))

    return model_class(**kwargs)


def _build_common_kwargs(
    doc_metadata: Any,
    chunk_metadata: dict[str, Any],
    ezshare_id: str | None,
    collection_name: str | None,
    blob_name: str | None,
) -> dict[str, Any]:
    """Build kwargs for common fields."""
    return {
        # Common document-level fields
        "document_type": getattr(doc_metadata, "document_type", None),
        "country": getattr(doc_metadata, "country", None),
        "year": getattr(doc_metadata, "year", None),
        "language": getattr(doc_metadata, "language", None),
        "disclosed": getattr(doc_metadata, "disclosed", None),
        "tags": getattr(doc_metadata, "tags", []),
        "department": getattr(doc_metadata, "department", None),
        "source": getattr(doc_metadata, "source", None),
        "document_name": getattr(doc_metadata, "document_name", None),
        "document_author": getattr(doc_metadata, "document_author", None),
        "file_extension": getattr(doc_metadata, "file_extension", None),
        "ezshare_id": ezshare_id,
        "collection_name": collection_name,
        "blob_name": blob_name,
        # Chunk-level fields
        "page_number": chunk_metadata.get("page_number"),
        "section_path": chunk_metadata.get("section_path"),
        "has_table": chunk_metadata.get("has_table"),
        "table_id": chunk_metadata.get("table_id"),
        "model_version": chunk_metadata.get("model_version"),
        "token_count": chunk_metadata.get("token_count"),
        "chunking_strategy": chunk_metadata.get("chunking_strategy"),
        "chunk_size": chunk_metadata.get("chunk_size"),
        "overlap_chars": chunk_metadata.get("overlap_chars"),
    }


def _build_operational_kwargs(doc_metadata: Any) -> dict[str, Any]:
    """Build kwargs for operational-specific fields."""
    doc_publish_date = _to_utc_datetime_offset(
        getattr(doc_metadata, "document_publish_date", None)
    )
    doc_approval_date = _to_utc_datetime_offset(
        getattr(doc_metadata, "document_approval_date", None)
    )

    return {
        "operation_number": getattr(doc_metadata, "operation_number", None),
        "sector": getattr(doc_metadata, "sector", None),
        "operation_type": getattr(doc_metadata, "operation_type", None),
        "dept_id": getattr(doc_metadata, "dept_id", None),
        "access_to_information_policy": getattr(
            doc_metadata, "access_to_information_policy", None
        ),
        "document_publish_date": doc_publish_date,
        "document_approval_date": doc_approval_date,
    }


def _build_publication_kwargs(doc_metadata: Any) -> dict[str, Any]:
    """Build kwargs for publication-specific fields."""
    pub_date = _to_utc_datetime_offset(getattr(doc_metadata, "publication_date", None))

    return {
        "journal": getattr(doc_metadata, "journal", None),
        "doi": getattr(doc_metadata, "doi", None),
        "issn": getattr(doc_metadata, "issn", None),
        "peer_reviewed": getattr(doc_metadata, "peer_reviewed", None),
        "publication_type": getattr(doc_metadata, "publication_type", None),
        "publication_date": pub_date,
    }


def _to_utc_datetime_offset(value: Any) -> str | None:
    """Convert datetime-like values to UTC DateTimeOffset string.

    Azure AI Search DateTimeOffset fields require an explicit timezone offset.
    """
    if value is None:
        return None

    parsed: datetime | None = None

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    elif hasattr(value, "isoformat"):
        iso_value = value.isoformat()
        try:
            parsed = datetime.fromisoformat(str(iso_value).replace("Z", "+00:00"))
        except ValueError:
            return str(iso_value)
    else:
        return str(value)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)

    return parsed.isoformat().replace("+00:00", "Z")


# Backward compatibility: Keep the old class method API working
# by adding the factory method to the base class
BaseSearchableMetadata.from_document_and_chunk = staticmethod(create_searchable_metadata)  # type: ignore[attr-defined]
OperationalSearchableMetadata.from_document_and_chunk = staticmethod(create_searchable_metadata)  # type: ignore[attr-defined]
PublicationSearchableMetadata.from_document_and_chunk = staticmethod(create_searchable_metadata)  # type: ignore[attr-defined]
