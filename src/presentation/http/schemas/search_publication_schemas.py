"""Pydantic schemas for the publication document search endpoint."""

from pydantic import Field

from src.presentation.http.schemas.search_base_schemas import BaseSearchRequest


class PublicationSearchRequest(BaseSearchRequest):
    """Request schema for POST /api/v1/search/publications.

    Extends BaseSearchRequest with publication-specific filters.
    The document_type is hard-coded to "publication" by the route handler
    and cannot be overridden by the client.
    """

    # Publication-specific filters
    journal: str | None = Field(
        None,
        description="Filter by journal name (exact match)",
    )
    doi: str | None = Field(
        None,
        description="Filter by DOI (exact match)",
    )
    issn: str | None = Field(
        None,
        description="Filter by ISSN (exact match)",
    )
    peer_reviewed: bool | None = Field(
        None,
        description="Filter by peer-reviewed status",
    )
    publication_type: str | None = Field(
        None,
        description="Filter by publication type (exact match)",
    )
    publication_date_from: str | None = Field(
        None,
        description="Filter by publication date (ISO 8601) — lower bound",
    )
    publication_date_to: str | None = Field(
        None,
        description="Filter by publication date (ISO 8601) — upper bound",
    )
