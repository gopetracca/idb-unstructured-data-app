"""HTTP route handlers."""

from src.presentation.http.routes.chunking import router as chunking_router
from src.presentation.http.routes.document_management import (
    router as document_management_router,
)
from src.presentation.http.routes.document_upload_operational import (
    router as document_upload_operational_router,
)
from src.presentation.http.routes.document_upload_publication import (
    router as document_upload_publication_router,
)
from src.presentation.http.routes.vectorization import router as vectorization_router

__all__ = [
    "document_management_router",
    "document_upload_operational_router",
    "document_upload_publication_router",
    "chunking_router",
    "vectorization_router",
]
