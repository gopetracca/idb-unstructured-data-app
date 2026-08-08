"""FastAPI dependency that resolves the current authenticated user."""

import logging

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, SecurityScopes

from src.config.settings import get_settings
from src.container import Container
from src.presentation.http.auth.errors import AuthenticationError, AuthorizationError
from src.presentation.http.auth.models import CurrentUser
from src.presentation.http.auth.scopes import Scopes, accepted_literals
from src.presentation.http.auth.token_validator import TokenValidator

logger = logging.getLogger(__name__)

# Registered in OpenAPI as a Bearer security scheme.
# auto_error=False gives us full control over the 401 response.
_bearer_scheme = HTTPBearer(auto_error=False)

# Anonymous user returned in dev / CI when ENTRA_ID_ENABLED=false.
_ANONYMOUS_USER = CurrentUser(
    user_id="anonymous",
    tenant_id="local",
    email="dev@local",
    roles=[scope.value for scope in Scopes],
)


def granted_scopes(claims: dict) -> set[str]:
    """Return every scope the token grants, from both Entra permission models.

    Entra carries authorization in two different claims depending on how the
    caller obtained the token, and this API has live consumers of both:

    - ``roles``: a JSON **array** of Entra App Role values. Present on app-only
      (client-credentials) tokens and on user tokens where the user or their
      group is assigned to an App Role.
    - ``scp``: a **space-delimited string** of delegated permission values.
      Present only when a user is in the flow — including the on-behalf-of
      exchange the MCP server performs.

    The union is deliberate: a single route declaration serves both M2M and
    delegated callers without duplicating the scope matrix.

    ``scp`` MUST be split. Passing the raw string to a membership test turns it
    into substring matching, so a token holding ``documents.readonly`` would
    satisfy a ``documents.read`` requirement — a privilege escalation.
    """
    roles = claims.get("roles") or []
    if isinstance(roles, str):  # defensive: Entra sends an array, but never trust shape
        roles = roles.split()

    scp = claims.get("scp") or ""
    if isinstance(scp, list):  # defensive: some IdPs emit scp as an array
        scp_values = scp
    else:
        scp_values = scp.split()

    return {str(value) for value in (*roles, *scp_values) if value}


@inject
async def get_current_user(
    security_scopes: SecurityScopes,
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
    validator: TokenValidator = Depends(Provide[Container.token_validator]),
) -> CurrentUser:
    """Resolve the current user from the bearer token.

    Authorization is an exact-match check against the union of the token's
    ``roles`` (App Roles) and ``scp`` (delegated scopes) claims — see
    :func:`granted_scopes`. There is no scope implication: ``admin`` does not
    confer ``documents.read``.

    When ENTRA_ID_ENABLED=false, returns a synthetic anonymous user with all
    roles — route handler signatures remain identical across environments.

    Args:
        security_scopes: Required scopes declared on the route via Security(..., scopes=[...]).
        credentials:     Raw bearer credentials extracted by HTTPBearer.
        validator:       TokenValidator singleton from the DI container.

    Returns:
        CurrentUser with identity and the granted scopes from the validated JWT.

    Raises:
        AuthenticationError: Token is missing, malformed, invalid, or lacks identity claims.
        AuthorizationError:  Token is valid but lacks a required scope.
    """
    authenticate_value = (
        f'Bearer scope="{security_scopes.scope_str}"' if security_scopes.scopes else "Bearer"
    )

    settings = get_settings()
    if not settings.entra_id.enabled:
        return _ANONYMOUS_USER

    if credentials is None:
        raise AuthenticationError(
            detail="Missing bearer token",
            authenticate_value=authenticate_value,
        )

    claims = await validator.validate(credentials.credentials)

    token_scopes = granted_scopes(claims)
    for scope in security_scopes.scopes:
        # Either spelling of the permission satisfies the requirement: the
        # delegated scope (scp) or its App Role twin (roles). Not an implication
        # — both denote the same permission under different Entra models.
        if not (accepted_literals(scope) & token_scopes):
            raise AuthorizationError(
                required=security_scopes.scopes,
                authenticate_value=authenticate_value,
            )

    # A validly-signed token that omits the identity claims is an authentication
    # failure, not a server error — read defensively so it cannot surface as a 500.
    user_id = claims.get("oid")
    tenant_id = claims.get("tid")
    if not user_id or not tenant_id:
        missing = [name for name, value in (("oid", user_id), ("tid", tenant_id)) if not value]
        logger.warning("Token accepted by signature but missing identity claims: %s", missing)
        raise AuthenticationError(
            detail=f"Token missing required identity claims: {', '.join(missing)}",
            authenticate_value=authenticate_value,
        )

    return CurrentUser(
        user_id=user_id,
        tenant_id=tenant_id,
        email=claims.get("preferred_username"),
        roles=sorted(token_scopes),
    )
