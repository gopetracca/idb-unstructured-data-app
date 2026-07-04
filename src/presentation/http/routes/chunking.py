"""Document chunking HTTP routes."""

import logging
import uuid
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query, Security, status

from src.application.dto.chunking import ChunkDocumentRequest, ListChunksRequest
from src.application.use_cases.chunk_document import ChunkDocumentUseCase
from src.application.use_cases.list_chunks import ListChunksUseCase
from src.container import Container
from src.presentation.http.auth import CurrentUser, get_current_user
from src.presentation.http.tenant import TenantId
from src.core.errors import (
    ChunkingError,
    DocumentNotFoundError,
    InvalidChunkingStrategyError,
    TextNotFoundError,
)
from src.core.value_objects.chunking_strategy import ChunkingStrategy
from src.presentation.http.schemas.chunking import (
    ChunkDocumentRequestSchema,
    ChunkDocumentResponseSchema,
    ChunkSchema,
    ListChunksResponseSchema,
    PaginationSchema,
)
from src.presentation.http.schemas.document_analysis import ErrorResponseSchema

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chunks", tags=["chunks"])


@router.post(
    "",
    response_model=ChunkDocumentResponseSchema,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {
            "description": "Document chunking completed",
            "model": ChunkDocumentResponseSchema,
        },
        400: {
            "description": "Invalid request or unsupported strategy",
            "model": ErrorResponseSchema,
        },
        404: {
            "description": "Document or text not found",
            "model": ErrorResponseSchema,
        },
        500: {
            "description": "Internal server error",
            "model": ErrorResponseSchema,
        },
    },
    summary="Chunk a document",
    description="""
    Chunk a document's extracted text into smaller segments for vectorization.

    The document must have been previously processed by Document Intelligence,
    with the extracted text stored in the source container (default: 'text').
    The resulting chunks will be stored in the output container (default: 'chunks').

    Supported chunking strategies:
    - fixed_size: Uniform chunks with configurable size and overlap
    - semantic_chunking: Semantic-aware chunking (future)
    - markdown_aware: Markdown structure-aware chunking (future)
    - recursive_chunking: Hierarchical chunking (future)
    """,
)
@inject
async def chunk_document(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=["api.write"])],
    request: ChunkDocumentRequestSchema,
    tenant_id: TenantId,
    use_case: ChunkDocumentUseCase = Depends(Provide[Container.chunk_document_use_case]),
) -> ChunkDocumentResponseSchema:
    """
    Chunk a document's extracted text.

    Args:
        request: Chunk document request with file_id and strategy
        use_case: Injected ChunkDocumentUseCase

    Returns:
        ChunkDocumentResponseSchema with processing status and chunk info

    Raises:
        HTTPException: On validation errors, not found, or processing errors
    """
    correlation_id = str(uuid.uuid4())

    logger.info(
        f"Received chunk document request: file_id={request.file_id}, "
        f"correlation_id={correlation_id}"
    )

    try:
        # Convert HTTP schema to application DTO
        chunking_strategy = request.chunking_strategy or ChunkingStrategy.fixed_size()

        dto_request = ChunkDocumentRequest(
            file_id=request.file_id,
            tenant_id=tenant_id,
            source_container=request.source_container,
            output_container=request.output_container,
            chunking_strategy=chunking_strategy,
            correlation_id=correlation_id,
        )

        # Execute use case
        result = await use_case.execute(dto_request)

        logger.info(
            f"Document chunking completed: file_id={request.file_id}, "
            f"chunk_count={result.chunk_count}, "
            f"status={result.status}, correlation_id={correlation_id}"
        )

        return ChunkDocumentResponseSchema(
            file_id=result.file_id,
            status=result.status.value,
            chunk_count=result.chunk_count,
            chunks_url=result.chunks_url,
            chunking_strategy=result.chunking_strategy,
            correlation_id=result.correlation_id,
            processing_time_ms=result.processing_time_ms,
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

    except TextNotFoundError as e:
        logger.warning(
            f"Text not found: file_id={request.file_id}, "
            f"correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "TextNotFoundError",
                "message": e.message,
                "details": e.details,
                "correlation_id": correlation_id,
            },
        )

    except InvalidChunkingStrategyError as e:
        logger.warning(
            f"Invalid chunking strategy: strategy={e.strategy_name}, "
            f"correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "InvalidChunkingStrategyError",
                "message": e.message,
                "details": {
                    "strategy_name": e.strategy_name,
                    "supported_strategies": e.supported_strategies,
                },
                "correlation_id": correlation_id,
            },
        )

    except ChunkingError as e:
        logger.error(
            f"Document chunking failed: file_id={request.file_id}, "
            f"error={e.message}, correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "ChunkingError",
                "message": e.message,
                "details": e.details,
                "correlation_id": correlation_id,
            },
        )

    except Exception:
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
    response_model=ListChunksResponseSchema,
    responses={
        200: {
            "description": "Chunks retrieved successfully",
            "model": ListChunksResponseSchema,
        },
        404: {
            "description": "Document not found",
            "model": ErrorResponseSchema,
        },
    },
    summary="List chunks",
    description="""
    Retrieve a paginated list of chunks filtered by content ID or document ID.

    Returns chunk metadata including text preview, position, and page number.
    """,
)
@inject
async def list_chunks(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=["api.read"])],
    tenant_id: TenantId,
    content_id: str | None = Query(default=None, description="Filter by content ID (same as documentId for now)"),
    document_id: str | None = Query(default=None, description="Filter by document ID"),
    page_number: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    use_case: ListChunksUseCase = Depends(Provide[Container.list_chunks_use_case]),
) -> ListChunksResponseSchema:
    """
    List chunks filtered by content ID or document ID.

    Args:
        content_id: Content identifier (optional filter)
        document_id: Document identifier (optional filter)
        tenant_id: Tenant identifier
        page_number: Page number (1-indexed)
        page_size: Number of items per page
        use_case: Injected ListChunksUseCase

    Returns:
        ListChunksResponseSchema with chunk list and pagination

    Raises:
        HTTPException: On not found or other errors
    """
    # Use content_id or document_id (they're the same for now)
    file_id = content_id or document_id

    if not file_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either content_id or document_id must be provided",
        )

    try:
        result = await use_case.execute(
            ListChunksRequest(
                file_id=file_id,
                tenant_id=tenant_id,
                page=page_number,
                page_size=page_size,
            )
        )

        chunks = [
            ChunkSchema(
                chunk_id=chunk.chunk_id,
                chunk_index=chunk.chunk_index,
                text_preview=chunk.text_preview,
                char_count=chunk.char_count,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                page_number=chunk.page_number,
            )
            for chunk in result.chunks
        ]

        return ListChunksResponseSchema(
            file_id=result.file_id,
            chunk_count=result.chunk_count,
            chunks=chunks,
            pagination=PaginationSchema(
                page=result.page,
                page_size=result.page_size,
                total_pages=result.total_pages,
            ),
        )

    except DocumentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "DocumentNotFoundError",
                "message": e.message,
                "details": e.details,
            },
        )

    except Exception as e:
        logger.exception("Error listing chunks: file_id=%s", file_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "InternalServerError",
                "message": f"Failed to list chunks: {str(e)}",
            },
        )


@router.get(
    "/{id}",
    summary="Get a chunk",
    description="Retrieve a single chunk by ID.",
)
async def get_chunk(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=["api.read"])],
    id: str,
    tenant_id: TenantId,
):
    """
    Get a chunk by ID.

    Note: This endpoint is a placeholder. Full implementation requires
    parsing chunk ID and fetching from blob storage.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Get chunk endpoint not yet implemented",
    )


@router.delete(
    "/{id}",
    summary="Delete a chunk",
    description="Delete a chunk (cascades to embeddings).",
)
async def delete_chunk(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=["api.write"])],
    id: str,
    tenant_id: TenantId,
):
    """
    Delete a chunk and cascade to embeddings.

    Note: This endpoint is a placeholder. Full implementation requires
    cascade delete logic.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Delete chunk endpoint not yet implemented",
    )
