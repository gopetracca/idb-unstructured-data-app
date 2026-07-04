"""Security-contract guard tests (AIA-477 / AIA-476).

These tests inspect the generated OpenAPI schema (no network/DB needed) to lock
in two invariants:

- AIA-477: every registered operation requires authentication, except an
  explicit allowlist (health probes). Prevents a future route from shipping
  unprotected.
- AIA-476: the API does not expose a client-supplied tenant (no ``X-Tenant-Id``
  header parameter, no ``tenant_id`` query parameter, and no body ``tenant_id``
  field). The effective tenant is resolved server-side by
  ``src/presentation/http/tenant.py``.
"""

import pytest

from src.main import app

_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

# Operations intentionally reachable without authentication (probes only).
_AUTH_ALLOWLIST = {"/", "/health/live", "/health/ready"}


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


@pytest.mark.unit
def test_no_route_accepts_client_supplied_tenant_parameter(openapi_schema: dict) -> None:
    """No operation declares a tenant header or tenant_id query parameter."""
    offenders: list[str] = []
    for path, operations in openapi_schema["paths"].items():
        for method, operation in operations.items():
            if method not in _HTTP_METHODS:
                continue
            for param in operation.get("parameters", []):
                name = (param.get("name") or "").lower()
                if "tenant" in name:
                    offenders.append(
                        f"{method.upper()} {path} -> {param.get('in')}:{param.get('name')}"
                    )

    assert not offenders, f"Endpoints exposing a tenant parameter: {sorted(offenders)}"


@pytest.mark.unit
def test_request_body_schemas_do_not_expose_tenant_id(openapi_schema: dict) -> None:
    """No request-body schema exposes a 'tenant_id' property (inputs only).

    Response schemas may still carry tenant_id; the invariant is about not
    trusting client input.
    """
    schemas = openapi_schema.get("components", {}).get("schemas", {})

    request_schema_names: set[str] = set()
    for operations in openapi_schema["paths"].values():
        for method, operation in operations.items():
            if method not in _HTTP_METHODS:
                continue
            content = operation.get("requestBody", {}).get("content", {})
            for media in content.values():
                ref = media.get("schema", {}).get("$ref")
                if ref:
                    request_schema_names.add(ref.rsplit("/", 1)[-1])

    offenders = [
        name
        for name in request_schema_names
        if "tenant_id" in (schemas.get(name, {}).get("properties", {}) or {})
    ]
    assert not offenders, f"Request schemas still exposing tenant_id: {sorted(offenders)}"
