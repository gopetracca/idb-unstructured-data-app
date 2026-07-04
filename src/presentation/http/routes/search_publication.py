"""Search route for publication documents (feature-flagged)."""

import logging
import uuid
from typing import Annotated, Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Security, status

from src.application.dto.search_dto import SemanticSearchInput
from src.application.use_cases.semantic_search import SemanticSearchUseCase
from src.config.settings import get_settings
from src.container import Container
from src.core.errors import (
    EmbeddingError,
    IndexNotFoundError,
    UnsupportedFilterError,
    ValidationError,
    VectorDatabaseError,
)
from src.core.value_objects.search_mode import SearchMode
from src.presentation.http.auth import CurrentUser, Scopes, get_current_user
from src.presentation.http.routes.search_helpers import build_response, map_errors
from src.presentation.http.schemas.search_publication_schemas import PublicationSearchRequest
from src.presentation.http.schemas.search_schemas import SemanticSearchResponse
from src.presentation.http.tenant import TenantId

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/search/publications", tags=["search"])

_DEFAULT_SEARCH_MODE = SearchMode.HYBRID
_DEFAULT_ENABLE_RERANKER = False
_DOCUMENT_TYPE = "publication"

_DISABLED_RESPONSE = {
    "error": "ServiceUnavailable",
    "message": "Publications search is not yet available — publications have not been ingested.",
}


def _build_input_dto(
    request: PublicationSearchRequest,
    tenant_id: str,
    correlation_id: str,
) -> SemanticSearchInput:
    """Map PublicationSearchRequest to application DTO.

    Hard-codes document_type="publication". Operational-only fields are absent
    from PublicationSearchRequest so clients cannot pass them.

    Publication-specific filter fields that have no explicit slot in
    SemanticSearchInput are forwarded via the generic filters dict.
    """
    resolved_mode = request.search_mode or _DEFAULT_SEARCH_MODE
    resolved_reranker = (
        request.enable_reranker if request.enable_reranker is not None else _DEFAULT_ENABLE_RERANKER
    )

    # language is a common field supported by the adapter's filters dict
    extra: dict[str, Any] = {}
    if request.language is not None:
        extra["language"] = request.language

    # Note: publication-specific fields (journal, doi, issn, peer_reviewed,
    # publication_type, publication_date_from/to) are accepted in the schema
    # but are NOT yet forwarded to the adapter — the vector search adapter's
    # filter allowlist does not include them. They will be wired up once the
    # adapter is extended (tracked separately from this issue).
    merged_filters = {**(request.filters or {}), **extra} or None

    return SemanticSearchInput(
        tenant_id=tenant_id,
        query=request.query,
        index_name=request.index_name,
        top_k=request.top_k,
        min_score=request.min_score,
        file_ids=request.file_ids,
        document_type=_DOCUMENT_TYPE,
        tags=request.tags,
        department=request.department,
        source=request.source,
        country=request.country,
        disclosed=request.disclosed,
        year=request.year,
        year_min=request.year_min,
        year_max=request.year_max,
        document_author=request.document_author,
        file_extension=request.file_extension,
        document_name=request.document_name,
        ezshare_id=request.ezshare_id,
        filters=merged_filters,
        page_size=request.page_size,
        page_number=request.page_number,
        sort_by=request.sort_by,
        order=request.order,
        search_mode=resolved_mode,
        enable_reranker=resolved_reranker,
        reranker_profile=request.reranker_profile,
        include_metadata=request.include_metadata,
        correlation_id=correlation_id,
    )


@router.post(
    "",
    response_model=SemanticSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Search publication documents",
    description="""
    Search over publication document embeddings. Only publication-document filters are
    exposed — passing operational-only fields (operation_number, sector, etc.) is a
    schema error (422).

    The `document_type` is always `"publication"` and cannot be overridden.

    **Note:** This endpoint is currently disabled and returns `503 Service Unavailable`
    until publications have been ingested. Enable it by setting
    `PUBLICATIONS_SEARCH_ENABLED=true`.

    Supports three search modes:
    - **semantic** (vector-only): cosine similarity over embeddings.
    - **keyword** (BM25-only): full-text BM25 — best for exact terms, IDs, acronyms.
    - **hybrid** (default): vector + BM25 fused via Reciprocal Rank Fusion (RRF).
    """,
)
@inject
async def search_publications(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=[Scopes.SEARCH_QUERY])],
    request: PublicationSearchRequest,
    tenant_id: TenantId,
    use_case: SemanticSearchUseCase = Depends(Provide[Container.semantic_search_use_case]),
) -> SemanticSearchResponse:
    if not get_settings().publications_search_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_DISABLED_RESPONSE,
        )

    correlation_id = str(uuid.uuid4())
    logger.info(
        "Publication search request: mode=%s, query='%s...', index=%s, correlation_id=%s",
        request.search_mode or _DEFAULT_SEARCH_MODE,
        request.query[:50],
        request.index_name,
        correlation_id,
    )
    try:
        input_dto = _build_input_dto(request, tenant_id, correlation_id)
        output = await use_case.execute(input_dto)
        logger.info(
            "Publication search completed: results=%d, time=%dms, correlation_id=%s",
            output.total_results,
            output.search_time_ms,
            correlation_id,
        )
        return build_response(output, request.include_metadata, correlation_id)
    except (IndexNotFoundError, EmbeddingError, VectorDatabaseError, ValidationError, UnsupportedFilterError) as e:
        raise map_errors(e, correlation_id)
    except Exception:
        logger.exception("Unexpected error during publication search: correlation_id=%s", correlation_id)
        raise map_errors(Exception(), correlation_id)
