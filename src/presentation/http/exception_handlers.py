"""Exception handlers for mapping domain errors to HTTP responses."""

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from src.core.errors import (
    DocumentNotFoundError,
    DomainError,
    DuplicateDocumentError,
    FileSizeExceededError,
    InvalidFileTypeError,
    MetadataValidationError,
    StorageError,
)
from src.presentation.http.auth.errors import AuthenticationError, AuthorizationError


async def duplicate_document_handler(
    request: Request,
    exc: DuplicateDocumentError,
) -> JSONResponse:
    """Handle DuplicateDocumentError -> 409 Conflict."""
    return JSONResponse(
        status_code=409,
        content={
            "error": "DuplicateDocument",
            "message": exc.message,
            "details": {
                "ezshare_id": exc.ezshare_id,
                "existing_file_id": exc.existing_file_id,
            },
        },
    )


async def document_not_found_handler(
    request: Request,
    exc: DocumentNotFoundError,
) -> JSONResponse:
    """Handle DocumentNotFoundError -> 404 Not Found."""
    return JSONResponse(
        status_code=404,
        content={
            "error": "DocumentNotFound",
            "message": exc.message,
            "details": {
                "file_id": exc.file_id,
                "tenant_id": exc.tenant_id,
            },
        },
    )


async def invalid_file_type_handler(
    request: Request,
    exc: InvalidFileTypeError,
) -> JSONResponse:
    """Handle InvalidFileTypeError -> 400 Bad Request."""
    return JSONResponse(
        status_code=400,
        content={
            "error": "InvalidFileType",
            "message": exc.message,
            "details": {
                "provided_type": exc.mime_type,
                "allowed_types": exc.allowed_types,
            },
        },
    )


async def file_size_exceeded_handler(
    request: Request,
    exc: FileSizeExceededError,
) -> JSONResponse:
    """Handle FileSizeExceededError -> 413 Payload Too Large."""
    return JSONResponse(
        status_code=413,
        content={
            "error": "FileSizeExceeded",
            "message": exc.message,
            "details": {
                "size_bytes": exc.size_bytes,
                "max_size_bytes": exc.max_size_bytes,
            },
        },
    )


async def metadata_validation_handler(
    request: Request,
    exc: MetadataValidationError,
) -> JSONResponse:
    """Handle MetadataValidationError -> 422 Unprocessable Entity."""
    return JSONResponse(
        status_code=422,
        content={
            "error": "MetadataValidationError",
            "message": exc.message,
            "details": {
                "field": exc.field,
                "reason": exc.reason,
            },
        },
    )


async def storage_error_handler(
    request: Request,
    exc: StorageError,
) -> JSONResponse:
    """Handle StorageError -> 500 Internal Server Error."""
    return JSONResponse(
        status_code=500,
        content={
            "error": "StorageError",
            "message": "An internal storage error occurred",
            "details": {
                "operation": exc.operation,
            },
        },
    )


async def domain_error_handler(
    request: Request,
    exc: DomainError,
) -> JSONResponse:
    """Handle generic DomainError -> 400 Bad Request."""
    return JSONResponse(
        status_code=400,
        content={
            "error": "DomainError",
            "message": exc.message,
            "details": None,
        },
    )


async def authentication_error_handler(
    request: Request,
    exc: AuthenticationError,
) -> JSONResponse:
    """Handle AuthenticationError -> 401 Unauthorized."""
    return JSONResponse(
        status_code=401,
        headers={"WWW-Authenticate": exc.authenticate_value},
        content={
            "error": "Unauthorized",
            "message": exc.detail,
        },
    )


async def authorization_error_handler(
    request: Request,
    exc: AuthorizationError,
) -> JSONResponse:
    """Handle AuthorizationError -> 403 Forbidden."""
    return JSONResponse(
        status_code=403,
        headers={"WWW-Authenticate": exc.authenticate_value},
        content={
            "error": "Forbidden",
            "message": "Insufficient permissions",
            "details": {"required": exc.required},
        },
    )


async def pydantic_validation_error_handler(
    request: Request,
    exc: ValidationError,
) -> JSONResponse:
    """Handle Pydantic ValidationError raised inside Depends functions -> 422."""
    return JSONResponse(
        status_code=422,
        content={
            "error": "ValidationError",
            "message": "Request validation failed",
            "details": exc.errors(),
        },
    )


def register_exception_handlers(app) -> None:
    """Register all exception handlers with the FastAPI app."""
    app.add_exception_handler(AuthenticationError, authentication_error_handler)
    app.add_exception_handler(AuthorizationError, authorization_error_handler)
    app.add_exception_handler(DuplicateDocumentError, duplicate_document_handler)
    app.add_exception_handler(DocumentNotFoundError, document_not_found_handler)
    app.add_exception_handler(InvalidFileTypeError, invalid_file_type_handler)
    app.add_exception_handler(FileSizeExceededError, file_size_exceeded_handler)
    app.add_exception_handler(MetadataValidationError, metadata_validation_handler)
    app.add_exception_handler(StorageError, storage_error_handler)
    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_exception_handler(ValidationError, pydantic_validation_error_handler)
