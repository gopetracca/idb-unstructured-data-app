"""Document vectorization HTTP routes."""

import logging
import uuid
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query, Security, status

from src.application.dto.embedding import VectorizeChunksRequest
from src.application.use_cases.vectorize_chunks import VectorizeChunksUseCase
from src.container import Container
from src.presentation.http.auth import CurrentUser, get_current_user
from src.core.errors import (
    ChunksNotFoundError,
    DocumentNotFoundError,
    EmbeddingError,
    RateLimitError,
)
from src.presentation.http.schemas.document_analysis import ErrorResponseSchema
from src.presentation.http.schemas.vectorization import (
    SupportedModelsResponseSchema,
    VectorizeChunksRequestSchema,
    VectorizeChunksResponseSchema,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/embeddings", tags=["embeddings"])


@router.post(
    "",
    response_model=VectorizeChunksResponseSchema,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {
            "description": "Vectorization completed",
            "model": VectorizeChunksResponseSchema,
        },
        404: {
            "description": "Document or chunks not found",
            "model": ErrorResponseSchema,
        },
        429: {
            "description": "Rate limit exceeded",
            "model": ErrorResponseSchema,
        },
        500: {
            "description": "Internal server error",
            "model": ErrorResponseSchema,
        },
    },
    summary="Vectorize document chunks",
    description="""
    Generate vector embeddings for document chunks using Azure OpenAI.

    The document must have been previously chunked, with chunks stored in the
    source container (default: 'chunks'). The resulting embeddings will be
    stored in the output container (default: 'embeddings').

    Supported embedding models:
    - text-embedding-3-small: 1536 dimensions (default)
    - text-embedding-3-large: 3072 dimensions
    """,
)
@inject
async def vectorize_chunks(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=["api.write"])],
    request: VectorizeChunksRequestSchema,
    use_case: VectorizeChunksUseCase = Depends(Provide[Container.vectorize_chunks_use_case]),
) -> VectorizeChunksResponseSchema:
    """
    Vectorize chunks for a document.

    Args:
        request: Vectorize chunks request with file_id and embedding config
        use_case: Injected VectorizeChunksUseCase

    Returns:
        VectorizeChunksResponseSchema with processing status and embedding info

    Raises:
        HTTPException: On validation errors, not found, or processing errors
    """
    correlation_id = str(uuid.uuid4())

    logger.info(
        f"Received vectorize chunks request: file_id={request.file_id}, "
        f"model={request.embedding_model}, correlation_id={correlation_id}"
    )

    try:
        # Convert HTTP schema to application DTO
        dto_request = VectorizeChunksRequest(
            file_id=request.file_id,
            tenant_id=request.tenant_id,
            file_version=request.file_version,
            embedding_model=request.embedding_model,
            batch_size=request.batch_size,
            correlation_id=correlation_id,
        )

        # Execute use case
        result = await use_case.execute(dto_request)

        logger.info(
            f"Vectorization completed: file_id={request.file_id}, "
            f"embedded={result.embedded_chunks}, failed={result.failed_chunks}, "
            f"status={result.status}, correlation_id={correlation_id}"
        )

        return VectorizeChunksResponseSchema(
            file_id=result.file_id,
            status=result.status.value,
            total_chunks=result.total_chunks,
            embedded_chunks=result.embedded_chunks,
            failed_chunks=result.failed_chunks,
            embedding_model=result.embedding_model,
            embedding_dimension=result.embedding_dimension,
            embeddings_url=result.embeddings_url,
            correlation_id=result.correlation_id,
            processing_time_ms=result.processing_time_ms,
            error_message=result.error_message,
            created_at=result.created_at,
        )

    except DocumentNotFoundError as e:
        logger.warning(
            f"Document not found: file_id={request.file_id}, "
            f"correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "DocumentNotFoundError",
                "message": e.message,
                "details": e.details,
                "correlation_id": correlation_id,
            },
        )

    except ChunksNotFoundError as e:
        logger.warning(
            f"Chunks not found: file_id={request.file_id}, "
            f"correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "ChunksNotFoundError",
                "message": e.message,
                "details": e.details,
                "correlation_id": correlation_id,
            },
        )

    except RateLimitError as e:
        logger.warning(
            f"Rate limit exceeded: file_id={request.file_id}, "
            f"retry_after={e.retry_after_seconds}, correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "RateLimitError",
                "message": e.message,
                "details": e.details,
                "correlation_id": correlation_id,
            },
            headers={"Retry-After": str(int(e.retry_after_seconds or 60))},
        )

    except EmbeddingError as e:
        logger.error(
            f"Embedding generation failed: file_id={request.file_id}, "
            f"error={e.message}, correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "EmbeddingError",
                "message": e.message,
                "details": e.details,
                "correlation_id": correlation_id,
            },
        )

    except Exception as e:
        logger.exception(
            f"Unexpected error: file_id={request.file_id}, "
            f"correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "InternalServerError",
                "message": "An unexpected error occurred",
                "correlation_id": correlation_id,
            },
        )


@router.get(
    "",
    summary="List embeddings",
    description="List embeddings with pagination and filtering.",
)
async def list_embeddings(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=["api.read"])],
    content_id: str | None = Query(default=None, description="Filter by content ID"),
    chunk_id: str | None = Query(default=None, description="Filter by chunk ID"),
    document_id: str | None = Query(default=None, description="Filter by document ID"),
    page_number: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    tenant_id: str = Query(default="default", description="Tenant identifier"),
):
    """
    List embeddings filtered by content, chunk, or document ID.

    Note: This endpoint is a placeholder. Full implementation requires
    embedding tracking beyond chunk indices.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="List embeddings endpoint not yet implemented",
    )


@router.get(
    "/{id}",
    summary="Get an embedding",
    description="Retrieve a single embedding by ID.",
)
async def get_embedding(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=["api.read"])],
    id: str,
    tenant_id: str = Query(default="default", description="Tenant identifier"),
):
    """
    Get an embedding by ID.

    Note: This endpoint is a placeholder. Full implementation requires
    embedding ID tracking and blob storage access.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Get embedding endpoint not yet implemented",
    )


@router.delete(
    "/{id}",
    summary="Delete an embedding",
    description="Delete a specific embedding.",
)
async def delete_embedding(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=["api.write"])],
    id: str,
    tenant_id: str = Query(default="default", description="Tenant identifier"),
):
    """
    Delete an embedding.

    Note: This endpoint is a placeholder. Full implementation requires
    embedding deletion from blob storage and index.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Delete embedding endpoint not yet implemented",
    )
