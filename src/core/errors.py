"""Domain exceptions for the RAG pipeline."""


class DomainError(Exception):
    """Base exception for domain errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class DocumentProcessingError(DomainError):
    """Raised when document processing fails."""

    def __init__(
        self,
        message: str,
        file_id: str | None = None,
        stage: str | None = None,
        details: dict | None = None,
    ):
        super().__init__(message, details)
        self.file_id = file_id
        self.stage = stage


class UnsupportedFormatError(DomainError):
    """Raised when a document format is not supported."""

    def __init__(
        self,
        content_type: str,
        supported_formats: list[str] | None = None,
        details: dict | None = None,
    ):
        message = f"Unsupported document format: {content_type}"
        if supported_formats:
            message += f". Supported formats: {', '.join(supported_formats)}"
        super().__init__(message, details)
        self.content_type = content_type
        self.supported_formats = supported_formats or []


class DocumentNotFoundError(DomainError):
    """Raised when a document is not found."""

    def __init__(
        self,
        file_id: str,
        tenant_id: str | None = None,
        container: str | None = None,
        details: dict | None = None,
    ):
        message = f"Document with file_id '{file_id}' not found"
        if tenant_id:
            message += f" for tenant '{tenant_id}'"
        if container:
            message += f" in container '{container}'"
        super().__init__(message, details)
        self.file_id = file_id
        self.tenant_id = tenant_id
        self.container = container


class ValidationError(DomainError):
    """Raised when input validation fails."""

    def __init__(
        self,
        message: str,
        field: str | None = None,
        details: dict | None = None,
    ):
        super().__init__(message, details)
        self.field = field


class UnsupportedFilterError(DomainError):
    """Raised when unsupported search filters are provided."""

    def __init__(
        self,
        unsupported_filters: list[str],
        supported_filters: list[str],
        details: dict | None = None,
    ):
        message = (
            "Unsupported filters provided: "
            + ", ".join(sorted(unsupported_filters))
        )
        super().__init__(message, details)
        self.unsupported_filters = unsupported_filters
        self.supported_filters = supported_filters


class InvalidFileTypeError(DomainError):
    """Raised when an uploaded file has an invalid type."""

    def __init__(
        self,
        mime_type: str,
        allowed_types: list[str],
        details: dict | None = None,
    ):
        self.mime_type = mime_type
        self.allowed_types = allowed_types
        message = f"Invalid file type '{mime_type}'. Allowed types: {', '.join(allowed_types)}"
        super().__init__(message, details)


class FileSizeExceededError(DomainError):
    """Raised when an uploaded file exceeds the size limit."""

    def __init__(
        self,
        size_bytes: int,
        max_size_bytes: int,
        details: dict | None = None,
    ):
        self.size_bytes = size_bytes
        self.max_size_bytes = max_size_bytes
        size_mb = size_bytes / (1024 * 1024)
        max_mb = max_size_bytes / (1024 * 1024)
        message = f"File size {size_mb:.2f}MB exceeds maximum allowed size of {max_mb:.2f}MB"
        super().__init__(message, details)


class MetadataValidationError(DomainError):
    """Raised when metadata validation fails."""

    def __init__(
        self,
        field: str,
        reason: str,
        details: dict | None = None,
    ):
        self.field = field
        self.reason = reason
        message = f"Metadata validation failed for field '{field}': {reason}"
        super().__init__(message, details)


class StorageError(DomainError):
    """Raised when a storage operation fails."""

    def __init__(
        self,
        operation: str,
        reason: str,
        details: dict | None = None,
    ):
        self.operation = operation
        self.reason = reason
        message = f"Storage operation '{operation}' failed: {reason}"
        super().__init__(message, details)


class ChunkingError(DomainError):
    """Raised when document chunking fails."""

    def __init__(
        self,
        message: str,
        file_id: str | None = None,
        strategy: str | None = None,
        details: dict | None = None,
    ):
        super().__init__(message, details)
        self.file_id = file_id
        self.strategy = strategy


class InvalidChunkingStrategyError(DomainError):
    """Raised when an invalid chunking strategy is specified."""

    def __init__(
        self,
        strategy_name: str,
        supported_strategies: list[str] | None = None,
        details: dict | None = None,
    ):
        message = f"Invalid chunking strategy: {strategy_name}"
        if supported_strategies:
            message += f". Supported strategies: {', '.join(supported_strategies)}"
        super().__init__(message, details)
        self.strategy_name = strategy_name
        self.supported_strategies = supported_strategies or []


class DocumentTooLargeError(DomainError):
    """Raised when a document exceeds size limits for processing."""

    def __init__(
        self,
        file_id: str,
        size_bytes: int,
        max_size_bytes: int,
        details: dict | None = None,
    ):
        message = (
            f"Document {file_id} is too large for processing: "
            f"{size_bytes} bytes (max: {max_size_bytes} bytes)"
        )
        super().__init__(message, details)
        self.file_id = file_id
        self.size_bytes = size_bytes
        self.max_size_bytes = max_size_bytes


class TextNotFoundError(DomainError):
    """Raised when extracted text is not found for a document."""

    def __init__(
        self,
        file_id: str,
        container: str | None = None,
        details: dict | None = None,
    ):
        message = f"Extracted text not found for document: {file_id}"
        if container:
            message += f" in container '{container}'"
        super().__init__(message, details)
        self.file_id = file_id
        self.container = container


class EmbeddingError(DomainError):
    """Raised when embedding generation fails."""

    def __init__(
        self,
        message: str,
        file_id: str | None = None,
        chunk_id: str | None = None,
        model: str | None = None,
        details: dict | None = None,
    ):
        super().__init__(message, details)
        self.file_id = file_id
        self.chunk_id = chunk_id
        self.model = model


class RateLimitError(DomainError):
    """Raised when rate limit is exceeded."""

    def __init__(
        self,
        message: str,
        retry_after_seconds: float | None = None,
        details: dict | None = None,
    ):
        super().__init__(message, details)
        self.retry_after_seconds = retry_after_seconds


class ChunksNotFoundError(DomainError):
    """Raised when chunks are not found for a file."""

    def __init__(
        self,
        file_id: str,
        container: str | None = None,
        details: dict | None = None,
    ):
        message = f"Chunks not found for file: {file_id}"
        if container:
            message += f" in container '{container}'"
        super().__init__(message, details)
        self.file_id = file_id
        self.container = container


# Vector Database Errors


class VectorDatabaseError(DomainError):
    """Base exception for vector database operations."""

    def __init__(
        self,
        message: str,
        index_name: str | None = None,
        operation: str | None = None,
        details: dict | None = None,
    ):
        super().__init__(message, details)
        self.index_name = index_name
        self.operation = operation


class IndexNotFoundError(VectorDatabaseError):
    """Raised when a vector database index is not found."""

    def __init__(
        self,
        index_name: str,
        details: dict | None = None,
    ):
        message = f"Vector database index not found: {index_name}"
        super().__init__(message, index_name=index_name, details=details)


class IndexAlreadyExistsError(VectorDatabaseError):
    """Raised when trying to create an index that already exists."""

    def __init__(
        self,
        index_name: str,
        details: dict | None = None,
    ):
        message = f"Vector database index already exists: {index_name}"
        super().__init__(message, index_name=index_name, details=details)


class VectorDimensionMismatchError(VectorDatabaseError):
    """Raised when vector dimensions don't match index schema."""

    def __init__(
        self,
        expected_dimension: int,
        actual_dimension: int,
        index_name: str | None = None,
        details: dict | None = None,
    ):
        message = (
            f"Vector dimension mismatch: expected {expected_dimension}, "
            f"got {actual_dimension}"
        )
        super().__init__(message, index_name=index_name, details=details)
        self.expected_dimension = expected_dimension
        self.actual_dimension = actual_dimension


class EmbeddingModelMismatchError(VectorDatabaseError):
    """Raised when document embedding model doesn't match collection's embedding model."""

    def __init__(
        self,
        expected_model: str,
        actual_model: str,
        collection_name: str | None = None,
        document_id: str | None = None,
        details: dict | None = None,
    ):
        message = (
            f"Embedding model mismatch: collection uses '{expected_model}', "
            f"but document was created with '{actual_model}'"
        )
        if document_id:
            message += f" (document_id: {document_id})"
        super().__init__(message, index_name=collection_name, details=details)
        self.expected_model = expected_model
        self.actual_model = actual_model
        self.document_id = document_id


class DuplicateDocumentError(DomainError):
    """Raised when attempting to upload a document with an existing ezshare_id."""

    def __init__(
        self,
        ezshare_id: str,
        existing_file_id: str,
        details: dict | None = None,
    ):
        self.ezshare_id = ezshare_id
        self.existing_file_id = existing_file_id
        message = f"Document with ezshare_id '{ezshare_id}' already exists (file_id: {existing_file_id})"
        super().__init__(message, details)
