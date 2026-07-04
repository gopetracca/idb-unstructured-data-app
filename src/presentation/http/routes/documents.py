"""Document analysis HTTP routes.

NOTE: this router is not currently registered in ``src/main.py`` — the content
extraction surface was refactored to ``/api/v1/contents`` (see ``contents.py``).
It is kept importable and secured defensively (AIA-477) so it cannot be wired
up unauthenticated by mistake.
"""

import logging
import uuid
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Security, status

from src.application.dto.document_analysis import DocumentAnalysisRequest
from src.application.use_cases.process_document import ProcessDocumentUseCase
from src.container import Container
from src.core.errors import (
    DocumentNotFoundError,
    DocumentProcessingError,
    UnsupportedFormatError,
)
from src.presentation.http.auth import CurrentUser, get_current_user
from src.presentation.http.schemas.document_analysis import (
    DocumentAnalysisRequestSchema,
    DocumentAnalysisResponseSchema,
    ErrorResponseSchema,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "/analyze",
    response_model=DocumentAnalysisResponseSchema,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {
            "description": "Document analysis started",
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
    summary="Analyze a document",
    description="""
    Analyze a document using Azure Document Intelligence and extract text as markdown.

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
async def analyze_document(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=["api.write"])],
    request: DocumentAnalysisRequestSchema,
    use_case: ProcessDocumentUseCase = Depends(Provide[Container.process_document_use_case]),
) -> DocumentAnalysisResponseSchema:
    """
    Analyze a document and extract text as markdown.

    Args:
        user: Authenticated caller (requires the write scope).
        request: Document analysis request with file_id and container info
        use_case: Injected ProcessDocumentUseCase

    Returns:
        DocumentAnalysisResponseSchema with processing status and output URL

    Raises:
        HTTPException: On validation errors, not found, or processing errors
    """
    correlation_id = str(uuid.uuid4())

    logger.info(
        f"Received document analysis request: file_id={request.file_id}, "
        f"correlation_id={correlation_id}"
    )

    try:
        # Convert HTTP schema to application DTO
        dto_request = DocumentAnalysisRequest(
            file_id=request.file_id,
            tenant_id=request.tenant_id,
            source_container=request.source_container,
            output_container=request.output_container,
            correlation_id=correlation_id,
        )

        # Execute use case
        result = await use_case.execute(dto_request)

        logger.info(
            f"Document analysis completed: file_id={request.file_id}, "
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
    "/supported-formats",
    response_model=list[str],
    summary="Get supported document formats",
    description="Returns a list of supported MIME types for document analysis.",
)
@inject
async def get_supported_formats(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=["api.read"])],
    use_case: ProcessDocumentUseCase = Depends(Provide[Container.process_document_use_case]),
) -> list[str]:
    """
    Get the list of supported document formats.

    Returns:
        List of supported MIME type strings
    """
    return use_case._document_intelligence.get_supported_formats()
