"""HTTP request/response schemas."""

from src.presentation.http.schemas.document_analysis import (
    DocumentAnalysisRequestSchema,
    DocumentAnalysisResponseSchema,
    ErrorResponseSchema,
)
from src.presentation.http.schemas.document_schemas import (
    DeleteDocumentResponse,
    DocumentSchema,
    ErrorResponse,
    ListDocumentsResponse,
    MetadataSchema,
    PaginationSchema,
    UpdateMetadataRequest,
    UpdateMetadataResponse,
    UploadDocumentResponse,
)
from src.presentation.http.schemas.vectorization import (
    EmbeddingSchema,
    ListEmbeddingsResponseSchema,
    SupportedModelsResponseSchema,
    VectorizeChunksRequestSchema,
    VectorizeChunksResponseSchema,
)

__all__ = [
    # Document analysis schemas
    "DocumentAnalysisRequestSchema",
    "DocumentAnalysisResponseSchema",
    "ErrorResponseSchema",
    # Document management schemas
    "DeleteDocumentResponse",
    "DocumentSchema",
    "ErrorResponse",
    "ListDocumentsResponse",
    "MetadataSchema",
    "PaginationSchema",
    "UpdateMetadataRequest",
    "UpdateMetadataResponse",
    "UploadDocumentResponse",
    # Vectorization schemas
    "EmbeddingSchema",
    "ListEmbeddingsResponseSchema",
    "SupportedModelsResponseSchema",
    "VectorizeChunksRequestSchema",
    "VectorizeChunksResponseSchema",
]
