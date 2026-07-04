"""Search route for operational documents."""

import logging
import uuid
from typing import Annotated, Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Security, status

from src.application.dto.search_dto import SemanticSearchInput
from src.application.use_cases.semantic_search import SemanticSearchUseCase
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
from src.presentation.http.schemas.search_operational_schemas import OperationalSearchRequest
from src.presentation.http.schemas.search_schemas import SemanticSearchResponse
from src.presentation.http.tenant import TenantId

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/search/operational", tags=["search"])

_DEFAULT_SEARCH_MODE = SearchMode.HYBRID
_DEFAULT_ENABLE_RERANKER = False


def _build_input_dto(
    request: OperationalSearchRequest,
    tenant_id: str,
    correlation_id: str,
) -> SemanticSearchInput:
    """Map OperationalSearchRequest to application DTO.

    The document_type filter is now user-provided (e.g., "PCR", "Report") rather
    than a hardcoded schema discriminator. Publication-only fields are absent
    from OperationalSearchRequest so clients cannot pass them.
    """
    resolved_mode = request.search_mode or _DEFAULT_SEARCH_MODE
    resolved_reranker = (
        request.enable_reranker if request.enable_reranker is not None else _DEFAULT_ENABLE_RERANKER
    )

    # Merge operational-only fields that have no explicit slot in SemanticSearchInput
    # into the generic filters dict so the vector adapter can apply them.
    extra: dict[str, Any] = {}
    if request.access_to_information_policy is not None:
        extra["access_to_information_policy"] = request.access_to_information_policy
    if request.language is not None:
        extra["language"] = request.language

    merged_filters = {**(request.filters or {}), **extra} or None

    return SemanticSearchInput(
        tenant_id=tenant_id,
        query=request.query,
        index_name=request.index_name,
        top_k=request.top_k,
        min_score=request.min_score,
        file_ids=request.file_ids,
        document_type=request.document_type,  # User-provided filter (e.g., "PCR", "Report")
        tags=request.tags,
        department=request.department,
        source=request.source,
        operation_number=request.operation_number,
        sector=request.sector,
        country=request.country,
        operation_type=request.operation_type,
        dept_id=request.dept_id,
        disclosed=request.disclosed,
        year=request.year,
        year_min=request.year_min,
        year_max=request.year_max,
        document_author=request.document_author,
        file_extension=request.file_extension,
        document_name=request.document_name,
        ezshare_id=request.ezshare_id,
        document_publish_date_from=request.document_publish_date_from,
        document_publish_date_to=request.document_publish_date_to,
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
    summary="Search operational documents",
    description="""
    Search over operational document embeddings. Only operational-document filters are
    exposed — passing publication-only fields (journal, doi, etc.) is a schema error (422).

    Optionally filter by `document_type` (e.g., `"PCR"`, `"Report"`, `"LP"`) to narrow
    results to a specific document classification within operational documents.

    Supports three search modes:
    - **semantic** (vector-only): cosine similarity over embeddings.
    - **keyword** (BM25-only): full-text BM25 — best for exact terms, IDs, acronyms.
    - **hybrid** (default): vector + BM25 fused via Reciprocal Rank Fusion (RRF).

    When `enable_reranker=true`, the Azure L2 semantic reranker re-scores top results.

    **Per-result `metadata`** (returned when `include_metadata=true`, default):
    `filename`, `document_name`, `page_number`, `section_path`, `ezshare_id`,
    `operation_number`, `document_author`, `country`, `sector`, `dept_id`, `year`.
    Callers can derive their own text preview from the `text` field if needed.
    """,
)
@inject
async def search_operational(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=[Scopes.SEARCH_QUERY])],
    request: OperationalSearchRequest,
    tenant_id: TenantId,
    use_case: SemanticSearchUseCase = Depends(Provide[Container.semantic_search_use_case]),
) -> SemanticSearchResponse:
    correlation_id = str(uuid.uuid4())
    logger.info(
        "Operational search request: mode=%s, query='%s...', index=%s, correlation_id=%s",
        request.search_mode or _DEFAULT_SEARCH_MODE,
        request.query[:50],
        request.index_name,
        correlation_id,
    )
    try:
        input_dto = _build_input_dto(request, tenant_id, correlation_id)
        output = await use_case.execute(input_dto)
        logger.info(
            "Operational search completed: results=%d, time=%dms, correlation_id=%s",
            output.total_results,
            output.search_time_ms,
            correlation_id,
        )
        return build_response(output, request.include_metadata, correlation_id)
    except (IndexNotFoundError, EmbeddingError, VectorDatabaseError, ValidationError, UnsupportedFilterError) as e:
        raise map_errors(e, correlation_id)
    except Exception:
        logger.exception("Unexpected error during operational search: correlation_id=%s", correlation_id)
        raise map_errors(Exception(), correlation_id)
