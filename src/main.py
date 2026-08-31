"""FastAPI application entry point for EA Unstructured Data API.

This module provides the main FastAPI application instance with a basic health
check endpoint and the versioned business routers.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config.settings import get_settings
from src.container import Container, verify_extraction_configuration
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


class AuthConfigurationError(RuntimeError):
    """Startup aborted because authentication is unsafe or unusable as configured."""


def verify_auth_configuration(settings) -> None:
    """Fail closed on an unsafe or unusable authentication configuration (AIA-482).

    Two failure modes, both of which previously produced only a log line:

    1. **Auth disabled outside development.** ``ENTRA_ID_ENABLED`` defaults to
       false, and when it is false every request resolves to an anonymous user
       holding every scope. A deploy that forgets the variable therefore serves
       the entire API unauthenticated. Refusing to start converts that silent
       exposure into an obvious, immediate deployment failure.
    2. **Auth enabled but incomplete.** Without a tenant and client id the
       validator cannot build an issuer, JWKS URI, or audience, so every request
       would 401 regardless of the token presented.

    ``ALLOW_ANONYMOUS_AUTH=true`` is the deliberate escape hatch for running a
    non-development build locally; it is never set in a deployed environment.

    Raises:
        AuthConfigurationError: If the configuration is unsafe or unusable.
    """
    if settings.entra_id.enabled:
        if not settings.entra_id.is_configured:
            raise AuthConfigurationError(
                "ENTRA_ID_ENABLED=true but the app registration is not fully configured "
                "(ENTRA_ID_TENANT_ID and ENTRA_ID_CLIENT_ID are both required). "
                "Every request would be rejected — refusing to start."
            )
        logger.info(
            "Authentication: Entra ID enabled (tenant=%s, audiences=%s)",
            settings.entra_id.tenant_id,
            settings.entra_id.accepted_audiences,
        )
        return

    if settings.is_development or settings.allow_anonymous_auth:
        logger.warning(
            "Authentication: DISABLED — all requests accepted anonymously "
            "(environment=%s). This is only permitted outside a deployed environment.",
            settings.environment,
        )
        return

    raise AuthConfigurationError(
        f"Authentication is disabled (ENTRA_ID_ENABLED=false) in environment "
        f"'{settings.environment}'. Every endpoint would be reachable without a token. "
        "Set ENTRA_ID_ENABLED=true, or set ALLOW_ANONYMOUS_AUTH=true to acknowledge "
        "running without authentication. Refusing to start."
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown."""
    # Startup
    logger.info("Starting EA Unstructured Data API")

    # Fail closed before serving traffic — must precede any dependency setup so a
    # misconfigured deploy dies fast instead of coming up unauthenticated.
    verify_auth_configuration(get_settings())

    # Initialize container and wire dependencies
    container = Container()
    container.wire()
    app.state.container = container

    # Build the configured extraction engine before serving. A deployment that cannot
    # extract should fail its readiness probe, not discover the problem one document at a
    # time — see `verify_extraction_configuration`.
    verify_extraction_configuration(container)

    # Initialize Azure storage containers/tables
    await initialize_storage()

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
