import atexit
import asyncio
import logging
import os

# Bootstrap Datadog inside the Python worker process before any src imports.
# The container entrypoint still wraps the Functions host with serverless-init,
# but Azure Functions can spawn a separate Python worker, so keep the in-code
# bootstrap for queue-trigger and ASGI execution paths.
#
# `ddtrace.auto` enables the full set of supported integrations (FastAPI,
# azure_functions, httpx, requests, pyodbc, openai, etc.). The compatibility
# layer needs Azure Container Apps metadata and is skipped for local Docker.
# Do not set DD_AGENT_HOST or DD_TRACE_AGENT_URL here; Datadog's serverless
# integrations derive the trace intake from their runtime configuration.
try:
    import ddtrace.auto  # noqa: F401  (import-for-side-effects: enables auto-instrumentation)

    if os.getenv("DD_AZURE_SUBSCRIPTION_ID") and os.getenv("DD_AZURE_RESOURCE_GROUP"):
        from datadog_serverless_compat import start as _datadog_serverless_start

        _datadog_serverless_start()
except Exception as _dd_exc:
    logging.getLogger(__name__).warning("Datadog bootstrap failed: %s", _dd_exc)

import azure.functions as func

from src.container import Container
from src.main import app as fastapi_app
from src.presentation.queue.triggers.chunk_document_trigger import bp as chunk_document_bp
from src.presentation.queue.triggers.ingest_into_db_trigger import bp as ingest_into_db_bp
from src.presentation.queue.triggers.process_text_trigger import bp as process_text_bp
from src.presentation.queue.triggers.vectorize_chunks_trigger import bp as vectorize_chunks_bp
from src.utils.base_logger import configure_logging

configure_logging()

# Initialize container and wire dependencies for queue triggers
container = Container()
container.wire()

# app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
app = func.AsgiFunctionApp(app=fastapi_app, http_auth_level=func.AuthLevel.ANONYMOUS)

# Add blueprints
app.register_functions(process_text_bp)
app.register_functions(chunk_document_bp)
app.register_functions(vectorize_chunks_bp)
app.register_functions(ingest_into_db_bp)


def _shutdown_resources() -> None:
    """Shutdown and cleanup all container resources."""
    try:
        asyncio.run(container.shutdown_resources())
    except RuntimeError:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(container.shutdown_resources())
    try:
        from ddtrace import tracer
        tracer.flush()
    except Exception:
        pass


atexit.register(_shutdown_resources)
