"""SearchResultMetadata value object.

Minimal metadata returned in the search API response. LLM-friendly — provides
only citation and follow-up query context, not the full filtering payload.

Derived at response time from SearchableMetadata + the blob_name from the
Document entity.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.core.value_objects.searchable_metadata import SearchableMetadata


class SearchResultMetadata(BaseModel):
    """Minimal metadata included in each search result returned to the caller."""

    filename: str | None = Field(default=None)
    page_number: int | None = Field(default=None)
    ezshare_id: str | None = Field(default=None)
    section_path: str | None = Field(default=None)
    year: int | None = Field(default=None)

    @classmethod
    def from_searchable(cls, searchable: SearchableMetadata) -> "SearchResultMetadata":
        """Derive SearchResultMetadata from SearchableMetadata (no SQL needed)."""
        return cls(
            filename=searchable.blob_name,
            page_number=searchable.page_number,
            ezshare_id=searchable.ezshare_id,
            section_path=searchable.section_path,
            year=searchable.year,
        )
