"""Pydantic schemas for the operational document search endpoint."""

from enum import StrEnum

from pydantic import Field

from src.presentation.http.schemas.search_base_schemas import BaseSearchRequest


class OperationalSortBy(StrEnum):
    """Sort fields available for operational document search."""

    SCORE = "score"
    YEAR = "year"
    DOCUMENT_PUBLISH_DATE = "document_publish_date"
    DOCUMENT_NAME = "document_name"
    OPERATION_NUMBER = "operation_number"
    COUNTRY = "country"
    SECTOR = "sector"
    DEPARTMENT = "department"
    SOURCE = "source"


class OperationalSearchRequest(BaseSearchRequest):
    """Request schema for POST /api/v1/search/operational.

    Extends BaseSearchRequest with operational-specific filters.
    The document_type is hard-coded to "operational" by the route handler
    and cannot be overridden by the client.
    """

    # Override index_name and enable_reranker defaults for operational documents
    index_name: str = Field(
        default="np-d-operational",
        description="Target vector index name",
    )
    enable_reranker: bool | None = Field(
        default=False,
        description="Enable Azure semantic L2 reranker. Defaults to False.",
    )

    # Override sort_by to expose only operational-relevant fields
    sort_by: OperationalSortBy | None = Field(
        None,
        description="Sort field for results (defaults to score desc)",
    )

    # Operational-specific filters
    operation_number: str | None = Field(
        None,
        description="Filter by operation number (exact match)",
    )
    sector: str | list[str] | None = Field(
        None,
        description="Filter by sector (exact match or list for OR logic)",
    )
    operation_type: str | None = Field(
        None,
        description="Filter by operation type (exact match)",
    )
    dept_id: str | None = Field(
        None,
        description="Filter by department ID (exact match)",
    )
    access_to_information_policy: str | None = Field(
        None,
        description="Filter by access to information policy",
    )
    document_publish_date_from: str | None = Field(
        None,
        description="Filter by document publish date (ISO 8601) — lower bound",
    )
    document_publish_date_to: str | None = Field(
        None,
        description="Filter by document publish date (ISO 8601) — upper bound",
    )
