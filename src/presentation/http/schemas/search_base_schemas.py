"""Base Pydantic schemas shared by all type-specific search endpoints."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.core.value_objects.search_mode import SearchMode


class SortOrder(StrEnum):
    """Sort order for search results."""

    ASC = "asc"
    DESC = "desc"


class BaseSortBy(StrEnum):
    """Sort fields common to all document types."""

    SCORE = "score"
    YEAR = "year"
    DOCUMENT_NAME = "document_name"
    COUNTRY = "country"
    DEPARTMENT = "department"
    SOURCE = "source"
    DOCUMENT_TYPE = "document_type"


class BaseSearchRequest(BaseModel):
    """Common request fields for all type-specific search endpoints.

    Subclass this to add document-type-specific filters. The document_type
    field is intentionally absent — each typed route hard-codes its own value.

    extra="forbid" ensures type-specific subclasses reject fields that belong
    to a different document type (e.g., journal on the operational endpoint).
    """

    model_config = ConfigDict(extra="forbid")

    # Required
    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural language search query",
    )

    # Search configuration
    index_name: str = Field(
        default="embeddings",
        description="Target vector index name",
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of results to return",
    )
    min_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum relevance score threshold",
    )

    # Common filters
    file_ids: list[str] | None = Field(
        None,
        max_length=50,
        description="Filter by specific file IDs",
    )
    tags: list[str] | None = Field(
        None,
        description="Filter by tags (AND logic)",
    )
    department: str | None = Field(
        None,
        description="Filter by department",
    )
    source: str | None = Field(
        None,
        description="Filter by source",
    )
    country: str | list[str] | None = Field(
        None,
        description="Filter by country (exact match or list for OR logic)",
    )
    language: str | None = Field(
        None,
        description="Filter by language (e.g., 'en', 'es')",
    )
    disclosed: bool | None = Field(
        None,
        description="Filter by disclosure status",
    )
    year: int | None = Field(
        None,
        ge=1900,
        le=2100,
        description="Filter by publication year (exact match)",
    )
    year_min: int | None = Field(
        None,
        ge=1900,
        le=2100,
        description="Filter by minimum publication year",
    )
    year_max: int | None = Field(
        None,
        ge=1900,
        le=2100,
        description="Filter by maximum publication year",
    )
    document_author: str | None = Field(
        None,
        description="Filter by document author (partial match)",
    )
    file_extension: str | None = Field(
        None,
        description="Filter by file extension (e.g., .pdf)",
    )
    document_name: str | None = Field(
        None,
        description="Filter by document name (exact match)",
    )
    ezshare_id: str | None = Field(
        None,
        description="Filter by EZShare ID (exact match)",
    )
    filters: dict[str, Any] | None = Field(
        None,
        description="Advanced filters (key/value pairs matching supported filter names)",
    )

    # Pagination and sorting
    page_size: int | None = Field(
        None,
        ge=1,
        le=100,
        description="Page size (max 100). Overrides top_k when provided.",
    )
    page_number: int | None = Field(
        None,
        ge=1,
        description="Page number (1-based). Defaults to 1 when page_size is set.",
    )
    sort_by: BaseSortBy | None = Field(
        None,
        description="Sort field for results (defaults to score desc)",
    )
    order: SortOrder | None = Field(
        None,
        description="Sort order (asc or desc)",
    )

    # Search mode
    search_mode: SearchMode | None = Field(
        default=None,
        description="Search mode: semantic (vector-only), keyword (BM25), or hybrid (default).",
    )
    enable_reranker: bool | None = Field(
        default=None,
        description="Enable Azure semantic L2 reranker. Defaults to False.",
    )
    reranker_profile: str | None = Field(
        default=None,
        max_length=200,
        description="Optional semantic reranker profile name.",
    )

    # Response options
    include_metadata: bool = Field(
        default=True,
        description="Include result metadata (filename, page, ezshare_id, etc.)",
    )
