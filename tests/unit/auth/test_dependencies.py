"""Unit tests for get_current_user dependency."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.security import HTTPAuthorizationCredentials, SecurityScopes

from src.config.settings import EntraIDSettings
from src.presentation.http.auth.dependencies import get_current_user
from src.presentation.http.auth.errors import AuthenticationError, AuthorizationError
from src.presentation.http.auth.models import CurrentUser
from src.presentation.http.auth.token_validator import TokenValidator

_VALID_CLAIMS = {
    "oid": "user-oid-123",
    "tid": "tenant-guid",
    "preferred_username": "user@example.com",
    "roles": ["api.read"],
}


def _credentials(token: str = "mock.jwt.token") -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _scopes(*scopes: str) -> SecurityScopes:
    mock = MagicMock(spec=SecurityScopes)
    mock.scopes = list(scopes)
    mock.scope_str = " ".join(scopes)
    return mock


def _mock_validator(claims: dict = _VALID_CLAIMS) -> TokenValidator:
    validator = MagicMock(spec=TokenValidator)
    validator.validate = AsyncMock(return_value=claims)
    return validator


# ---------------------------------------------------------------------------
# Feature flag disabled — anonymous user
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_returns_anonymous_user_when_auth_disabled() -> None:
    disabled_settings = EntraIDSettings(enabled=False)

    with patch("src.presentation.http.auth.dependencies.get_settings", return_value=MagicMock(entra_id=disabled_settings)):
        user = await get_current_user(
            security_scopes=_scopes("api.read"),
            credentials=None,
            validator=_mock_validator(),
        )

    assert user.user_id == "anonymous"
    assert "api.read" in user.roles
    assert "api.write" in user.roles


# ---------------------------------------------------------------------------
# Auth enabled
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_raises_authentication_error_when_no_credentials() -> None:
    enabled_settings = EntraIDSettings(enabled=True, tenant_id="t", client_id="c")

    with patch("src.presentation.http.auth.dependencies.get_settings", return_value=MagicMock(entra_id=enabled_settings)):
        with pytest.raises(AuthenticationError, match="Missing bearer token"):
            await get_current_user(
                security_scopes=_scopes("api.read"),
                credentials=None,
                validator=_mock_validator(),
            )


@pytest.mark.unit
async def test_returns_current_user_on_valid_token_with_correct_scope() -> None:
    enabled_settings = EntraIDSettings(enabled=True, tenant_id="t", client_id="c")

    with patch("src.presentation.http.auth.dependencies.get_settings", return_value=MagicMock(entra_id=enabled_settings)):
        user = await get_current_user(
            security_scopes=_scopes("api.read"),
            credentials=_credentials(),
            validator=_mock_validator(),
        )

    assert isinstance(user, CurrentUser)
    assert user.user_id == "user-oid-123"
    assert user.tenant_id == "tenant-guid"
    assert user.email == "user@example.com"
    assert user.roles == ["api.read"]


@pytest.mark.unit
async def test_raises_authorization_error_when_scope_missing() -> None:
    enabled_settings = EntraIDSettings(enabled=True, tenant_id="t", client_id="c")
    claims_read_only = {**_VALID_CLAIMS, "roles": ["api.read"]}

    with patch("src.presentation.http.auth.dependencies.get_settings", return_value=MagicMock(entra_id=enabled_settings)):
        with pytest.raises(AuthorizationError) as exc_info:
            await get_current_user(
                security_scopes=_scopes("api.write"),
                credentials=_credentials(),
                validator=_mock_validator(claims_read_only),
            )

    assert "api.write" in exc_info.value.required


@pytest.mark.unit
async def test_authenticate_value_includes_scope_string_when_scopes_declared() -> None:
    enabled_settings = EntraIDSettings(enabled=True, tenant_id="t", client_id="c")

    with patch("src.presentation.http.auth.dependencies.get_settings", return_value=MagicMock(entra_id=enabled_settings)):
        with pytest.raises(AuthorizationError) as exc_info:
            await get_current_user(
                security_scopes=_scopes("api.admin"),
                credentials=_credentials(),
                validator=_mock_validator(),
            )

    assert 'scope="api.admin"' in exc_info.value.authenticate_value


@pytest.mark.unit
async def test_validator_exception_propagates_as_authentication_error() -> None:
    enabled_settings = EntraIDSettings(enabled=True, tenant_id="t", client_id="c")
    validator = MagicMock(spec=TokenValidator)
    validator.validate = AsyncMock(side_effect=AuthenticationError("Token has expired"))

    with patch("src.presentation.http.auth.dependencies.get_settings", return_value=MagicMock(entra_id=enabled_settings)):
        with pytest.raises(AuthenticationError, match="expired"):
            await get_current_user(
                security_scopes=_scopes("api.read"),
                credentials=_credentials(),
                validator=validator,
            )
