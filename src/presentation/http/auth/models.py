"""Auth models — domain representation of the authenticated caller."""

from pydantic import BaseModel


class CurrentUser(BaseModel):
    """Authenticated caller extracted from a validated Entra ID JWT.

    Attributes:
        user_id:   Object ID (oid claim) — stable across apps, safe to store on records.
        tenant_id: Azure AD tenant GUID (tid claim).
        email:     Principal name (preferred_username) — not always present in app tokens.
        roles:     App roles assigned to the caller (roles claim).
    """

    user_id: str
    tenant_id: str
    email: str | None
    roles: list[str]
