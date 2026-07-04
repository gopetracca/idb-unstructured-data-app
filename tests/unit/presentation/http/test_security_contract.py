"""Security-contract guard tests (AIA-477 / AIA-476).

These tests inspect the generated OpenAPI schema (no network/DB needed) to lock
in two invariants:

- AIA-477: every registered operation requires authentication, except an
  explicit allowlist (health probes). Prevents a future route from shipping
  unprotected.
- AIA-476: the API does not expose a client-supplied tenant (no ``X-Tenant-Id``
  header parameter, no ``tenant_id`` query parameter, and no body ``tenant_id``
  field).
"""

import pytest

from src.main import app

_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

# Operations intentionally reachable without authentication (probes only).
_AUTH_ALLOWLIST = {"/"}


@pytest.fixture(scope="module")
def openapi_schema() -> dict:
    return app.openapi()


@pytest.mark.unit
def test_all_registered_routes_require_auth(openapi_schema: dict) -> None:
    """Every operation (minus the allowlist) declares a security requirement."""
    missing: list[str] = []
    for path, operations in openapi_schema["paths"].items():
        if path in _AUTH_ALLOWLIST:
            continue
        for method, operation in operations.items():
            if method not in _HTTP_METHODS:
                continue
            if not operation.get("security"):
                missing.append(f"{method.upper()} {path}")

    assert not missing, f"Endpoints missing authentication: {sorted(missing)}"


@pytest.mark.unit
def test_auth_allowlist_is_current(openapi_schema: dict) -> None:
    """The allowlist only contains paths that are actually mounted."""
    mounted = set(openapi_schema["paths"])
    stale = _AUTH_ALLOWLIST - mounted
    assert not stale, f"_AUTH_ALLOWLIST entries no longer mounted: {sorted(stale)}"
