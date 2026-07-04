"""Authorization-scope contract test (AIA-481).

Locks in the resource-oriented 4-scope model: every mounted operation must
require exactly the scope from the mapping below. Fails when a route is added,
removed, or its scope drifts — update the mapping deliberately when the API
surface changes.

Verb rule: GET → documents.read, POST/PATCH → documents.write, DELETE → admin;
plus search.query for /search/* and admin for /collections/* and /analytics/*.
"""

import pytest
from fastapi.routing import APIRoute

from src.main import app
from src.presentation.http.auth import get_current_user
from src.presentation.http.auth.scopes import Scopes

# Public operations (no auth, no scope) — keep in sync with test_security_contract.
_PUBLIC: set[tuple[str, str]] = {
    ("GET", "/"),
    ("GET", "/health/live"),
    ("GET", "/health/ready"),
}

_EXPECTED_SCOPES: dict[tuple[str, str], str] = {
    # --- search (read-side RAG consumption) ---
    ("POST", "/api/v1/search"): Scopes.SEARCH_QUERY,
    ("POST", "/api/v1/search/operational"): Scopes.SEARCH_QUERY,
    ("POST", "/api/v1/search/publications"): Scopes.SEARCH_QUERY,
    # --- discovery / reads ---
    ("GET", "/api/v1/capabilities"): Scopes.DOCUMENTS_READ,
    ("GET", "/api/v1/documents"): Scopes.DOCUMENTS_READ,
    ("GET", "/api/v1/documents/{id}"): Scopes.DOCUMENTS_READ,
    ("GET", "/api/v1/contents"): Scopes.DOCUMENTS_READ,
    ("GET", "/api/v1/contents/{id}"): Scopes.DOCUMENTS_READ,
    ("GET", "/api/v1/contents/{id}/text"): Scopes.DOCUMENTS_READ,
    ("GET", "/api/v1/chunks"): Scopes.DOCUMENTS_READ,
    ("GET", "/api/v1/chunks/{id}"): Scopes.DOCUMENTS_READ,
    ("GET", "/api/v1/embeddings"): Scopes.DOCUMENTS_READ,
    ("GET", "/api/v1/embeddings/{id}"): Scopes.DOCUMENTS_READ,
    # --- ingestion / pipeline writes ---
    ("POST", "/api/v1/documents"): Scopes.DOCUMENTS_WRITE,
    ("POST", "/api/v1/documents/operational"): Scopes.DOCUMENTS_WRITE,
    ("POST", "/api/v1/documents/publication"): Scopes.DOCUMENTS_WRITE,
    ("PATCH", "/api/v1/documents/{id}"): Scopes.DOCUMENTS_WRITE,
    ("POST", "/api/v1/contents"): Scopes.DOCUMENTS_WRITE,
    ("POST", "/api/v1/chunks"): Scopes.DOCUMENTS_WRITE,
    ("POST", "/api/v1/embeddings"): Scopes.DOCUMENTS_WRITE,
    # --- destructive deletes ---
    ("DELETE", "/api/v1/documents/{id}"): Scopes.ADMIN,
    ("DELETE", "/api/v1/contents/{id}"): Scopes.ADMIN,
    ("DELETE", "/api/v1/chunks/{id}"): Scopes.ADMIN,
    ("DELETE", "/api/v1/embeddings/{id}"): Scopes.ADMIN,
    # --- collection/index administration ---
    ("POST", "/api/v1/collections"): Scopes.ADMIN,
    ("GET", "/api/v1/collections"): Scopes.ADMIN,
    ("GET", "/api/v1/collections/{collection_name}"): Scopes.ADMIN,
    ("DELETE", "/api/v1/collections/{collection_name}"): Scopes.ADMIN,
    ("POST", "/api/v1/collections/{collection_name}/reranker"): Scopes.ADMIN,
    ("POST", "/api/v1/collections/{collection_name}/documents"): Scopes.ADMIN,
    # --- analytics / observability ---
    ("GET", "/api/v1/analytics/stage-durations"): Scopes.ADMIN,
    ("GET", "/api/v1/documents/{file_id}/processing-timeline"): Scopes.ADMIN,
}


def _declared_scopes(route: APIRoute) -> list[str] | None:
    """Extract the scopes declared on the route's get_current_user dependency."""

    def _walk(dependant) -> list[str] | None:
        for sub in dependant.dependencies:
            if sub.call is get_current_user:
                declared = getattr(sub, 'own_oauth_scopes', None) or getattr(sub, 'security_scopes', None)
                return [str(scope) for scope in (declared or [])]
            found = _walk(sub)
            if found is not None:
                return found
        return None

    return _walk(route.dependant)


def _mounted_operations() -> dict[tuple[str, str], APIRoute]:
    operations: dict[tuple[str, str], APIRoute] = {}
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods - {"HEAD", "OPTIONS"}:
                operations[(method, route.path)] = route
    return operations


@pytest.mark.unit
def test_scope_mapping_covers_every_mounted_operation() -> None:
    mounted = set(_mounted_operations()) - _PUBLIC
    unmapped = mounted - set(_EXPECTED_SCOPES)
    removed = set(_EXPECTED_SCOPES) - mounted
    assert not unmapped, f"Operations missing from the scope mapping: {sorted(unmapped)}"
    assert not removed, f"Mapped operations no longer mounted: {sorted(removed)}"


@pytest.mark.unit
def test_every_operation_requires_its_mapped_scope() -> None:
    operations = _mounted_operations()
    mismatches: list[str] = []
    for key, expected in _EXPECTED_SCOPES.items():
        route = operations.get(key)
        if route is None:
            continue  # covered by the coverage test above
        declared = _declared_scopes(route)
        if declared != [expected]:
            mismatches.append(f"{key[0]} {key[1]}: declared={declared} expected=[{expected}]")
    assert not mismatches, "Scope drift detected:\n" + "\n".join(sorted(mismatches))


@pytest.mark.unit
def test_no_legacy_scope_literals_remain() -> None:
    """The old api.read / api.write / api.admin literals must not be declared anywhere."""
    legacy = {"api.read", "api.write", "api.admin"}
    offenders: list[str] = []
    for (method, path), route in _mounted_operations().items():
        declared = _declared_scopes(route) or []
        if legacy & set(declared):
            offenders.append(f"{method} {path}: {declared}")
    assert not offenders, f"Legacy scopes still declared: {sorted(offenders)}"
