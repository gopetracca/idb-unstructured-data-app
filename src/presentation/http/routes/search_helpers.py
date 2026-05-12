"""Shared helpers for all search route handlers."""

from fastapi import HTTPException, status

from src.core.errors import (
    EmbeddingError,
    IndexNotFoundError,
    UnsupportedFilterError,
    ValidationError,
    VectorDatabaseError,
)
from src.core.value_objects.search_result_metadata import SearchResultMetadata
from src.presentation.http.schemas.search_schemas import (
    SearchResultSchema,
    SemanticSearchResponse,
)


def build_response(output, include_metadata: bool, correlation_id: str) -> SemanticSearchResponse:
    """Map use-case output to the HTTP response schema."""
    result_schemas = [
        SearchResultSchema(
            chunk_id=result.chunk_id,
            file_id=result.file_id,
            score=result.score,
            reranker_score=result.reranker_score,
            text=result.text,
            metadata=SearchResultMetadata.from_searchable(result.metadata) if include_metadata else None,
        )
        for result in output.results
    ]
    return SemanticSearchResponse(
        query=output.query,
        results=result_schemas,
        total_results=output.total_results,
        search_time_ms=output.search_time_ms,
        embedding_model=output.embedding_model,
        filters_applied=output.filters_applied,
        search_mode=output.search_mode,
        reranker_enabled=output.reranker_enabled,
        correlation_id=output.correlation_id,
    )


def map_errors(e: Exception, correlation_id: str) -> HTTPException:
    """Map domain errors to FastAPI HTTPExceptions."""
    if isinstance(e, IndexNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "IndexNotFoundError", "message": str(e), "correlation_id": correlation_id},
        )
    if isinstance(e, EmbeddingError):
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "EmbeddingError", "message": "Failed to generate query embedding", "correlation_id": correlation_id},
        )
    if isinstance(e, VectorDatabaseError):
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "VectorDatabaseError",
                "message": e.message,
                "details": e.details,
                "correlation_id": correlation_id,
            },
        )
    if isinstance(e, ValidationError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "ValidationError", "message": e.message, "details": e.details, "correlation_id": correlation_id},
        )
    if isinstance(e, UnsupportedFilterError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "UnsupportedFilterError", "message": e.message, "details": e.details, "correlation_id": correlation_id},
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"error": "InternalServerError", "message": "An unexpected error occurred during search", "correlation_id": correlation_id},
    )
