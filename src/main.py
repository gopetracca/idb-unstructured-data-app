"""FastAPI application entry point for EA Unstructured Data API.

This module provides the main FastAPI application instance with a basic health
check endpoint and the versioned business routers.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config.settings import get_settings
from src.container import Container
from src.infrastructure.initialization import initialize_storage
from src.presentation.http.exception_handlers import register_exception_handlers
from src.presentation.http.middleware.max_body_size import MaxBodySizeMiddleware
from src.presentation.http.routes.capabilities import router as capabilities_router
from src.presentation.http.routes.chunking import router as chunking_router
from src.presentation.http.routes.collections import router as collections_router
from src.presentation.http.routes.contents import router as contents_router
from src.presentation.http.routes.document_management import (
    router as document_management_router,
)
from src.presentation.http.routes.document_upload_operational import (
    router as document_upload_operational_router,
)
from src.presentation.http.routes.document_upload_publication import (
    router as document_upload_publication_router,
)
from src.presentation.http.routes.health import router as health_router
from src.presentation.http.routes.search import router as search_router
from src.presentation.http.routes.search_operational import router as search_operational_router
from src.presentation.http.routes.search_publication import router as search_publication_router
from src.presentation.http.routes.analytics import router as analytics_router
from src.presentation.http.routes.vectorization import router as vectorization_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown."""
    # Startup
    logger.info("Starting EA Unstructured Data API")

    # Initialize container and wire dependencies
    container = Container()
    container.wire()
    app.state.container = container

    # Initialize Azure storage containers/tables
    await initialize_storage()

    # Log auth status
    from src.config.settings import get_settings as _get_settings
    _settings = _get_settings()
    if _settings.entra_id.enabled:
        logger.info(
            "Authentication: Entra ID enabled (tenant=%s, audience=%s)",
            _settings.entra_id.tenant_id,
            _settings.entra_id.effective_audience,
        )
    else:
        logger.warning("Authentication: DISABLED — all requests accepted anonymously")

    yield

    # Shutdown
    logger.info("Shutting down EA Unstructured Data API")
    await container.shutdown_resources()


# Initialize FastAPI application
app = FastAPI(
    title="EA Unstructured Data API",
    description="Unstructured data processing API for AI applications",
    version="0.1.0",
    lifespan=lifespan,
)

# Register exception handlers
register_exception_handlers(app)

# Reject oversized request bodies before they are buffered (AIA-478).
# Multipart overhead headroom is added inside the middleware; the streaming
# byte counter covers chunked/understated Content-Length bodies.
app.add_middleware(
    MaxBodySizeMiddleware,
    max_file_size_bytes=get_settings().file_upload.max_file_size_bytes,
)

# Include routers
app.include_router(health_router)
app.include_router(capabilities_router)
app.include_router(document_management_router)
app.include_router(document_upload_operational_router)
app.include_router(document_upload_publication_router)
app.include_router(contents_router)
app.include_router(chunking_router)
app.include_router(vectorization_router)
app.include_router(search_router)
app.include_router(search_operational_router)
app.include_router(search_publication_router)
app.include_router(collections_router)
app.include_router(analytics_router)


# Route Handlers
@app.get("/")
async def root() -> dict[str, str]:
    """Liveness endpoint — process is up, no dependency I/O.

    Kept for backwards compatibility; the platform probes use /health/live
    (liveness) and /health/ready (readiness/startup) instead.

    Returns:
        dict[str, str]: Status information with service name.
    """
    return {"status": "ok", "service": "ea-unstructured-data"}
