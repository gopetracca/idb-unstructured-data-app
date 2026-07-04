"""Tenant resolution for the HTTP layer (AIA-476).

Security: the API must NOT trust a client-supplied tenant. Previously every
route accepted an ``X-Tenant-Id`` header, a ``tenant_id`` query parameter, or a
body ``tenant_id`` field and used it directly — allowing a caller authenticated
for one tenant to reach another tenant's data.

This module is the single place that decides the effective tenant. For now
(single-tenant phase) it returns the configured ``default_tenant_id``. The
multi-tenant plumbing in the use-cases and repositories is intentionally
preserved; to re-enable per-user multi-tenancy later, change
``get_effective_tenant_id`` to derive the tenant from the authenticated
``CurrentUser.tenant_id`` (the ``tid`` claim) — no route signatures need to
change.
"""

from typing import Annotated

from fastapi import Depends

from src.config.settings import get_settings


def get_effective_tenant_id() -> str:
    """Return the effective tenant id for the current request.

    Phase 1 (single-tenant): the configured default. Client-supplied tenant
    values are ignored by design — they are no longer accepted at the API
    boundary.
    """
    return get_settings().default_tenant_id


# Convenience annotation for route parameters: ``tenant_id: TenantId``.
TenantId = Annotated[str, Depends(get_effective_tenant_id)]
