"""Pydantic schemas for search API endpoints."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from src.core.value_objects.search_mode import SearchMode
from src.core.value_objects.search_result_metadata import SearchResultMetadata


class SortOrder(StrEnum):
    """Sort order for search results."""

    ASC = "asc"
    DESC = "desc"


class SearchSortBy(StrEnum):
    """Supported sort fields for search results."""

    SCORE = "score"
    YEAR = "year"
    DOCUMENT_PUBLISH_DATE = "document_publish_date"
    DOCUMENT_NAME = "document_name"
    OPERATION_NUMBER = "operation_number"
    COUNTRY = "country"
    SECTOR = "sector"
    DOCUMENT_TYPE = "document_type"
    DEPARTMENT = "department"
    SOURCE = "source"


class SemanticSearchRequest(BaseModel):
    """Request schema for semantic search endpoint."""

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

    # Filters (all optional)
    file_ids: list[str] | None = Field(
        None,
        max_length=50,
        description="Filter by specific file IDs",
    )
    document_type: str | None = Field(
        None,
        description="Filter by document type",
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
    operation_number: str | None = Field(
        None,
        description="Filter by operation number (exact match)",
    )
    sector: str | list[str] | None = Field(
        None,
        description="Filter by sector (exact match or list for OR logic)",
    )
    country: str | list[str] | None = Field(
        None,
        description="Filter by country (exact match or list for OR logic)",
    )
    operation_type: str | None = Field(
        None,
        description="Filter by operation type (exact match)",
    )
    dept_id: str | None = Field(
        None,
        description="Filter by department ID (exact match)",
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
    document_publish_date_from: str | None = Field(
        None,
        description="Filter by document publish date (ISO) - from",
    )
    document_publish_date_to: str | None = Field(
        None,
        description="Filter by document publish date (ISO) - to",
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
    sort_by: SearchSortBy | None = Field(
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
        description="Search mode: semantic (vector-only), keyword (BM25), or hybrid (vector+BM25 via RRF). Defaults to hybrid.",
    )
    enable_reranker: bool | None = Field(
        default=None,
        description="Enable Azure semantic L2 reranker. Defaults to False.",
    )
    reranker_profile: str | None = Field(
        default=None,
        max_length=200,
        description="Optional semantic reranker profile (Azure semantic configuration name) to use for this query.",
    )

    # Response options
    include_metadata: bool = Field(
        default=True,
        description="Include result metadata (filename, page, ezshare_id, etc.)",
    )


class SearchResultSchema(BaseModel):
    """Schema for a single search result."""

    chunk_id: str = Field(..., description="Chunk identifier")
    file_id: str = Field(..., description="Parent file identifier")
    score: float = Field(
        ...,
        ge=0.0,
        description="Relevance score (cosine similarity or RRF-fused)",
    )
    reranker_score: float | None = Field(
        default=None,
        ge=0.0,
        le=4.0,
        description="Azure semantic reranker score (0-4), present when reranker is enabled",
    )
    text: str = Field(..., description="Chunk text content")

    # LLM-friendly metadata for citation and follow-up context
    metadata: SearchResultMetadata | None = Field(
        default=None,
        description=(
            "Result metadata: filename, document_name, page_number, section_path, "
            "ezshare_id, operation_number, document_author, country, sector, dept_id, year"
        ),
    )


class SemanticSearchResponse(BaseModel):
    """Response schema for search endpoints."""

    query: str = Field(..., description="Original search query")
    results: list[SearchResultSchema] = Field(
        ...,
        description="Search results ordered by relevance",
    )
    total_results: int = Field(
        ...,
        ge=0,
        description="Number of results returned",
    )
    search_time_ms: int = Field(..., description="Total search execution time in milliseconds")
    embedding_model: str = Field(..., description="Model used for query vectorization")
    filters_applied: dict[str, Any] = Field(
        default_factory=dict,
        description="Filters that were applied",
    )
    search_mode: SearchMode = Field(..., description="Search mode used (semantic/keyword/hybrid)")
    reranker_enabled: bool = Field(..., description="Whether the Azure semantic reranker was applied")
    correlation_id: str = Field(..., description="Correlation ID for request tracing")


# Alias for backward compatibility
SearchResponse = SemanticSearchResponse
