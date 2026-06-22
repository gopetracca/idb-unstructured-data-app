"""SearchResultMetadata value object.

Metadata returned in the search API response per result. LLM-friendly — provides
citation and follow-up query context derived at response time from
SearchableMetadata (the typed projection of the vector index per chunk).

No SQL lookup is required: every field below is already populated on the
vector index for operational documents. Publication results may have some
operational-only fields (operation_number, sector, dept_id) as None.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.core.value_objects.searchable_metadata import SearchableMetadata


class SearchResultMetadata(BaseModel):
    """Metadata included in each search result returned to the caller."""

    # File / chunk anchors
    filename: str | None = Field(default=None)
    document_name: str | None = Field(default=None)
    page_number: int | None = Field(default=None)
    section_path: str | None = Field(default=None)

    # External identifiers
    ezshare_id: str | None = Field(default=None)
    operation_number: str | None = Field(default=None)

    # Document-level descriptors
    document_type: str | None = Field(default=None)
    document_author: str | None = Field(default=None)
    country: str | None = Field(default=None)
    sector: str | None = Field(default=None)
    dept_id: str | None = Field(default=None)
    year: int | None = Field(default=None)

    @classmethod
    def from_searchable(cls, searchable: SearchableMetadata) -> "SearchResultMetadata":
        """Derive SearchResultMetadata from SearchableMetadata (no SQL needed).

        Uses getattr for operational-only fields so publication results
        (which don't carry operation_number/sector/dept_id) still project cleanly.
        """
        return cls(
            filename=searchable.blob_name,
            document_name=searchable.document_name,
            page_number=searchable.page_number,
            section_path=searchable.section_path,
            ezshare_id=searchable.ezshare_id,
            operation_number=getattr(searchable, "operation_number", None),
            document_type=searchable.document_type,
            document_author=searchable.document_author,
            country=searchable.country,
            sector=getattr(searchable, "sector", None),
            dept_id=getattr(searchable, "dept_id", None),
            year=searchable.year,
        )
