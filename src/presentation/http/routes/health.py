"""Health probe routes (AIA-479).

- ``GET /health/live``: liveness — the process is up. No dependency I/O, so a
  slow or failing downstream can never make the platform restart the replica.
- ``GET /health/ready``: readiness/startup — verifies the dependencies needed
  to serve traffic (SQL Server, Azure AI Search). Checks run concurrently with
  a bounded timeout and report a per-dependency status map; any failure yields
  503 so the replica is drained until it recovers.

Both endpoints are unauthenticated: Container Apps probes cannot send bearer
tokens. They expose no data beyond dependency reachability.
"""

import asyncio
import logging

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from src.container import Container

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])

# Probes must answer fast; the Container Apps probe timeout is 5s.
_CHECK_TIMEOUT_SECONDS = 4.0

_STATUS_OK = "ok"
_STATUS_DISABLED = "disabled"


@router.get(
    "/live",
    summary="Liveness probe",
    description="Process is up. Performs no dependency I/O.",
)
async def liveness() -> dict[str, str]:
    return {"status": "alive", "service": "ea-unstructured-data"}


async def _check_sql(session_factory) -> str:
    if session_factory is None:
        return _STATUS_DISABLED
    async with session_factory() as session:
        await session.execute(text("SELECT 1"))
    return _STATUS_OK


async def _check_search(vector_database) -> str:
    if not await vector_database.health_check():
        raise ConnectionError("Azure AI Search unreachable")
    return _STATUS_OK


async def _run_check(name: str, check) -> tuple[str, str, bool]:
    try:
        status_value = await asyncio.wait_for(check, timeout=_CHECK_TIMEOUT_SECONDS)
        return name, status_value, True
    except TimeoutError:
        logger.warning("Readiness check '%s' timed out after %ss", name, _CHECK_TIMEOUT_SECONDS)
        return name, "timeout", False
    except Exception as exc:
        logger.warning("Readiness check '%s' failed: %s", name, exc)
        return name, f"error: {type(exc).__name__}", False


@router.get(
    "/ready",
    summary="Readiness probe",
    description=(
        "Verifies critical dependencies (SQL Server, Azure AI Search) concurrently "
        "with bounded timeouts. Returns 200 when all pass, 503 with a per-dependency "
        "status map otherwise. Also used as the startup probe."
    ),
    responses={
        200: {"description": "All dependencies reachable"},
        503: {"description": "One or more dependencies unavailable"},
    },
)
@inject
async def readiness(
    session_factory=Depends(Provide[Container.sql_session_factory]),
    vector_database=Depends(Provide[Container.vector_database_adapter]),
) -> JSONResponse:
    results = await asyncio.gather(
        _run_check("sql", _check_sql(session_factory)),
        _run_check("search", _check_search(vector_database)),
    )

    checks = {name: status_value for name, status_value, _ in results}
    ready = all(passed for _, _, passed in results)

    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "checks": checks},
    )
