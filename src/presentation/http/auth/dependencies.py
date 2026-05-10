"""FastAPI dependency that resolves the current authenticated user."""

import logging

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, SecurityScopes

from src.config.settings import get_settings
from src.container import Container
from src.presentation.http.auth.errors import AuthenticationError, AuthorizationError
from src.presentation.http.auth.models import CurrentUser
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
    roles=["api.read", "api.write", "api.admin"],
)


@inject
async def get_current_user(
    security_scopes: SecurityScopes,
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
    validator: TokenValidator = Depends(Provide[Container.token_validator]),
) -> CurrentUser:
    """Resolve the current user from the bearer token.

    When ENTRA_ID_ENABLED=false, returns a synthetic anonymous user with all
    roles — route handler signatures remain identical across environments.

    Args:
        security_scopes: Required scopes declared on the route via Security(..., scopes=[...]).
        credentials:     Raw bearer credentials extracted by HTTPBearer.
        validator:       TokenValidator singleton from the DI container.

    Returns:
        CurrentUser with identity and roles from the validated JWT.

    Raises:
        AuthenticationError: Token is missing, malformed, or invalid.
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

    token_roles: list[str] = claims.get("roles", [])
    for scope in security_scopes.scopes:
        if scope not in token_roles:
            raise AuthorizationError(
                required=security_scopes.scopes,
                authenticate_value=authenticate_value,
            )

    return CurrentUser(
        user_id=claims["oid"],
        tenant_id=claims["tid"],
        email=claims.get("preferred_username"),
        roles=token_roles,
    )
