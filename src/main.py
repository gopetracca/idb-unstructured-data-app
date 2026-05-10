"""FastAPI application entry point for EA Unstructured Data API.

This module provides the main FastAPI application instance with basic health check
and echo endpoints for validating the Azure Functions + FastAPI integration.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, Field

from src.container import Container
from src.infrastructure.initialization import initialize_storage
from src.presentation.http.exception_handlers import register_exception_handlers
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

# Include routers
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


# Pydantic Models
class EchoRequest(BaseModel):
    """Request model for echo endpoint."""

    message: str = Field(..., description="Message to echo back", min_length=1)


class EchoResponse(BaseModel):
    """Response model for echo endpoint."""

    echo: str = Field(..., description="Echoed message")


# Route Handlers
@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint for health check.

    Returns:
        dict[str, str]: Status information with service name.
    """
    return {"status": "ok", "service": "ea-unstructured-data"}


@app.post("/echo")
async def echo_post(request: EchoRequest) -> EchoResponse:
    """Echo back the provided message via POST request.

    Args:
        request: EchoRequest containing the message to echo.

    Returns:
        EchoResponse: Response containing the echoed message.
    """
    return EchoResponse(echo=request.message)


@app.get("/echo/{message}")
async def echo_get(message: str) -> EchoResponse:
    """Echo back the provided message via GET request.

    Args:
        message: Message to echo back from path parameter.

    Returns:
        EchoResponse: Response containing the echoed message.
    """
    return EchoResponse(echo=message)
