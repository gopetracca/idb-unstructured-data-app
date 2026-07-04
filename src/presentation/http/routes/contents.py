"""Content extraction HTTP routes (refactored from documents.py)."""

import logging
import uuid
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query, Security, status

from src.application.dto.document_analysis import DocumentAnalysisRequest
from src.application.use_cases.process_document import ProcessDocumentUseCase
from src.container import Container
from src.presentation.http.auth import CurrentUser, Scopes, get_current_user
from src.core.errors import (
    DocumentNotFoundError,
    DocumentProcessingError,
    UnsupportedFormatError,
)
from src.presentation.http.schemas.document_analysis import (
    DocumentAnalysisRequestSchema,
    DocumentAnalysisResponseSchema,
    ErrorResponseSchema,
)
from src.presentation.http.tenant import TenantId

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/contents", tags=["contents"])


@router.post(
    "",
    response_model=DocumentAnalysisResponseSchema,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {
            "description": "Content extraction started",
            "model": DocumentAnalysisResponseSchema,
        },
        400: {
            "description": "Invalid request or unsupported format",
            "model": ErrorResponseSchema,
        },
        404: {
            "description": "Document not found",
            "model": ErrorResponseSchema,
        },
        500: {
            "description": "Internal server error",
            "model": ErrorResponseSchema,
        },
    },
    summary="Extract content from a document",
    description="""
    Extract text content from a document using Azure Document Intelligence.

    The document must already exist in the source container (default: 'raw').
    The extracted markdown will be stored in the output container (default: 'text').

    Supported formats:
    - PDF (application/pdf)
    - Word documents (application/vnd.openxmlformats-officedocument.wordprocessingml.document)
    - Images (PNG, JPEG, TIFF, BMP)
    - Plain text (text/plain)
    """,
)
@inject
async def create_content(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=[Scopes.DOCUMENTS_WRITE])],
    request: DocumentAnalysisRequestSchema,
    tenant_id: TenantId,
    use_case: ProcessDocumentUseCase = Depends(
        Provide[Container.process_document_use_case]
    ),
) -> DocumentAnalysisResponseSchema:
    """
    Extract content from a document.

    Args:
        request: Document analysis request with document_id (renamed from file_id in schema)
        use_case: Injected ProcessDocumentUseCase

    Returns:
        DocumentAnalysisResponseSchema with processing status and content URL

    Raises:
        HTTPException: On validation errors, not found, or processing errors
    """
    correlation_id = str(uuid.uuid4())

    logger.info(
        f"Received content extraction request: file_id={request.file_id}, "
        f"correlation_id={correlation_id}"
    )

    try:
        # Convert HTTP schema to application DTO
        dto_request = DocumentAnalysisRequest(
            file_id=request.file_id,
            tenant_id=tenant_id,
            source_container=request.source_container,
            output_container=request.output_container,
            correlation_id=correlation_id,
        )

        # Execute use case
        result = await use_case.execute(dto_request)

        logger.info(
            f"Content extraction completed: file_id={request.file_id}, "
            f"status={result.status}, correlation_id={correlation_id}"
        )

        return DocumentAnalysisResponseSchema(
            file_id=result.file_id,
            status=result.status.value,
            markdown_url=result.markdown_url,
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

    except UnsupportedFormatError as e:
        logger.warning(
            f"Unsupported format: content_type={e.content_type}, "
            f"correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "UnsupportedFormatError",
                "message": e.message,
                "details": {
                    "content_type": e.content_type,
                    "supported_formats": e.supported_formats,
                },
                "correlation_id": correlation_id,
            },
        )

    except DocumentProcessingError as e:
        logger.error(
            f"Document processing failed: file_id={request.file_id}, "
            f"error={e.message}, correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "DocumentProcessingError",
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
    summary="List contents",
    description="List extracted contents with pagination and filtering by document ID.",
)
async def list_contents(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=[Scopes.DOCUMENTS_READ])],
    tenant_id: TenantId,
    document_id: Annotated[
        str | None,
        Query(description="Filter by document ID"),
    ] = None,
    page_number: Annotated[
        int,
        Query(ge=1, description="Page number (1-indexed)"),
    ] = 1,
    page_size: Annotated[
        int,
        Query(ge=1, le=100, description="Items per page"),
    ] = 20,
):
    """
    List extracted contents.

    Note: This endpoint is a placeholder. Full implementation requires
    tracking content IDs separately from document IDs.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="List contents endpoint not yet implemented",
    )


@router.get(
    "/{id}",
    summary="Get content metadata",
    description="Retrieve metadata for a specific content extraction.",
)
async def get_content(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=[Scopes.DOCUMENTS_READ])],
    id: str,
    tenant_id: TenantId,
):
    """
    Get content metadata by ID.

    Note: This endpoint is a placeholder. Full implementation requires
    tracking content IDs separately from document IDs.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Get content endpoint not yet implemented",
    )


@router.get(
    "/{id}/text",
    summary="Get extracted text",
    description="Retrieve the raw extracted text/markdown content.",
)
async def get_content_text(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=[Scopes.DOCUMENTS_READ])],
    id: str,
    tenant_id: TenantId,
):
    """
    Get extracted text content.

    Note: This endpoint is a placeholder. Full implementation requires
    reading from blob storage.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Get content text endpoint not yet implemented",
    )


@router.delete(
    "/{id}",
    summary="Delete content",
    description="Delete extracted content (cascades to chunks and embeddings).",
)
async def delete_content(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=[Scopes.ADMIN])],
    id: str,
    tenant_id: TenantId,
):
    """
    Delete content and cascade to chunks/embeddings.

    Note: This endpoint is a placeholder. Full implementation requires
    cascade delete logic.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Delete content endpoint not yet implemented",
    )
