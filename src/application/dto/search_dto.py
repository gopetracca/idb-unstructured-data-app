"""Data Transfer Objects for search use cases."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from src.core.entities.search_result import SearchResult
from src.core.value_objects.search_mode import SearchMode


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


class SemanticSearchInput(BaseModel):
    """Input DTO for semantic search use case."""

    tenant_id: str = Field(..., description="Tenant identifier")
    query: str = Field(..., min_length=1, max_length=2000, description="Search query text")
    index_name: str = Field(default="embeddings", description="Vector index name")
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results to return")
    min_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum relevance score")

    # Filters
    file_ids: list[str] | None = Field(None, max_length=50, description="Filter by file IDs")
    document_type: str | None = Field(None, description="Filter by document type")
    tags: list[str] | None = Field(None, description="Filter by tags (AND logic)")
    department: str | None = Field(None, description="Filter by department")
    source: str | None = Field(None, description="Filter by source")
    operation_number: str | None = Field(None, description="Filter by operation number")
    sector: str | list[str] | None = Field(None, description="Filter by sector")
    country: str | list[str] | None = Field(None, description="Filter by country")
    operation_type: str | None = Field(None, description="Filter by operation type")
    dept_id: str | None = Field(None, description="Filter by department ID")
    disclosed: bool | None = Field(None, description="Filter by disclosure status")
    year: int | None = Field(None, ge=1900, le=2100, description="Filter by year")
    year_min: int | None = Field(None, ge=1900, le=2100, description="Filter by minimum year")
    year_max: int | None = Field(None, ge=1900, le=2100, description="Filter by maximum year")
    document_author: str | None = Field(None, description="Filter by document author")
    file_extension: str | None = Field(None, description="Filter by file extension")
    document_name: str | None = Field(None, description="Filter by document name")
    ezshare_id: str | None = Field(None, description="Filter by EZShare ID")
    document_publish_date_from: str | None = Field(
        None, description="Filter by document publish date (ISO) - from"
    )
    document_publish_date_to: str | None = Field(
        None, description="Filter by document publish date (ISO) - to"
    )
    filters: dict[str, Any] | None = Field(
        None, description="Advanced filters (key/value pairs)"
    )

    # Pagination and sorting
    page_size: int | None = Field(None, ge=1, le=100, description="Page size (max 100)")
    page_number: int | None = Field(None, ge=1, description="Page number (1-based)")
    sort_by: SearchSortBy | None = Field(None, description="Sort field")
    order: SortOrder | None = Field(None, description="Sort order")

    # Search mode
    search_mode: SearchMode = Field(default=SearchMode.HYBRID, description="Search mode")
    enable_reranker: bool = Field(default=False, description="Enable Azure semantic L2 reranker")
    reranker_profile: str | None = Field(
        default=None,
        description="Optional semantic reranker profile (Azure semantic configuration name)",
    )

    # Options
    include_metadata: bool = Field(default=True, description="Include enriched metadata")
    correlation_id: str = Field(..., description="Request correlation ID")


class SemanticSearchOutput(BaseModel):
    """Output DTO from search use case."""

    query: str = Field(..., description="Original search query")
    results: list[SearchResult] = Field(..., description="Search results")
    total_results: int = Field(..., ge=0, description="Number of results returned")
    search_time_ms: int = Field(..., description="Search execution time")
    embedding_model: str = Field(..., description="Embedding model used")
    filters_applied: dict[str, Any] = Field(
        default_factory=dict,
        description="Filters applied to search",
    )
    search_mode: SearchMode = Field(..., description="Search mode used")
    reranker_enabled: bool = Field(..., description="Whether the semantic reranker was applied")
    correlation_id: str = Field(..., description="Request correlation ID")
