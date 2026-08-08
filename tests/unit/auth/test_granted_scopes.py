"""Authorization across both Entra permission models (AIA-675).

This API is reached by two kinds of caller, and Entra expresses their
permissions in two different claims:

- app-only / client-credentials callers carry App Roles in ``roles`` (array)
- delegated callers — notably the MCP server's on-behalf-of exchange — carry
  delegated scopes in ``scp`` (space-delimited string)

``get_current_user`` authorizes on the union. These tests pin that behaviour,
including the substring hazard that makes the naive implementation unsafe.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.security import HTTPAuthorizationCredentials, SecurityScopes

from src.config.settings import EntraIDSettings
from src.presentation.http.auth.dependencies import get_current_user, granted_scopes
from src.presentation.http.auth.errors import AuthenticationError, AuthorizationError
from src.presentation.http.auth.scopes import Scopes, accepted_literals
from src.presentation.http.auth.token_validator import TokenValidator

_IDENTITY = {"oid": "user-oid-123", "tid": "tenant-guid"}


def _credentials(token: str = "mock.jwt.token") -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _scopes(*scopes: str) -> SecurityScopes:
    mock = MagicMock(spec=SecurityScopes)
    mock.scopes = list(scopes)
    mock.scope_str = " ".join(scopes)
    return mock


def _mock_validator(claims: dict) -> TokenValidator:
    validator = MagicMock(spec=TokenValidator)
    validator.validate = AsyncMock(return_value=claims)
    return validator


def _enabled_settings() -> MagicMock:
    return MagicMock(entra_id=EntraIDSettings(enabled=True, tenant_id="t", client_id="c"))


async def _authorize(claims: dict, *required: str):
    with patch(
        "src.presentation.http.auth.dependencies.get_settings",
        return_value=_enabled_settings(),
    ):
        return await get_current_user(
            security_scopes=_scopes(*required),
            credentials=_credentials(),
            validator=_mock_validator(claims),
        )


# ---------------------------------------------------------------------------
# granted_scopes — claim parsing
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_app_roles_claim_is_read_as_a_list() -> None:
    claims = {"roles": ["documents.read", "documents.write"]}
    assert granted_scopes(claims) == {"documents.read", "documents.write"}


@pytest.mark.unit
def test_delegated_scp_claim_is_split_on_whitespace() -> None:
    """scp is a space-delimited string, not an array."""
    claims = {"scp": "Search documents.read"}
    assert granted_scopes(claims) == {"Search", "documents.read"}


@pytest.mark.unit
def test_union_of_both_claims_is_returned() -> None:
    claims = {"roles": ["admin"], "scp": "Search"}
    assert granted_scopes(claims) == {"admin", "Search"}


@pytest.mark.unit
def test_missing_claims_yield_empty_set() -> None:
    assert granted_scopes({}) == set()
    assert granted_scopes({"roles": None, "scp": None}) == set()


@pytest.mark.unit
def test_single_delegated_scope_is_parsed() -> None:
    """The live MCP token shape: exactly one delegated scope, no roles claim."""
    assert granted_scopes({"scp": "Search"}) == {"Search"}


@pytest.mark.unit
@pytest.mark.parametrize(
    "scp_value",
    ["documents.readonly", "documents.read.limited", "xdocuments.read"],
)
def test_scp_is_not_matched_as_a_substring(scp_value: str) -> None:
    """Regression guard for a privilege-escalation bug.

    Passing the raw scp string to a membership test makes ``in`` a substring
    check, so ``documents.readonly`` would satisfy ``documents.read``.
    """
    assert "documents.read" not in granted_scopes({"scp": scp_value})


# ---------------------------------------------------------------------------
# get_current_user — end-to-end authorization for both caller types
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_delegated_token_with_search_scope_is_authorized() -> None:
    """The MCP on-behalf-of path: scp-only token reaching a search route."""
    user = await _authorize({**_IDENTITY, "scp": "Search"}, Scopes.SEARCH)

    assert user.user_id == "user-oid-123"
    assert "Search" in user.roles


@pytest.mark.unit
async def test_app_only_token_with_app_role_is_authorized() -> None:
    """The M2M path: roles-only token carrying the .All spelling."""
    user = await _authorize({**_IDENTITY, "roles": ["documents.write.All"]}, Scopes.DOCUMENTS_WRITE)

    assert "documents.write.All" in user.roles


# ---------------------------------------------------------------------------
# Dual spelling — Entra forbids one literal in both appRoles and
# oauth2PermissionScopes, so each permission has a delegated and a .All form.
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "required",
    [Scopes.SEARCH, Scopes.DOCUMENTS_READ, Scopes.DOCUMENTS_WRITE, Scopes.ADMIN],
)
def test_every_scope_accepts_both_spellings(required: Scopes) -> None:
    assert accepted_literals(required) == {required.value, f"{required.value}.All"}


@pytest.mark.unit
async def test_app_role_spelling_satisfies_a_delegated_requirement() -> None:
    user = await _authorize({**_IDENTITY, "roles": ["Search.All"]}, Scopes.SEARCH)

    assert "Search.All" in user.roles


@pytest.mark.unit
async def test_delegated_spelling_satisfies_the_same_requirement() -> None:
    user = await _authorize({**_IDENTITY, "scp": "Search"}, Scopes.SEARCH)

    assert "Search" in user.roles


@pytest.mark.unit
async def test_all_suffix_does_not_leak_across_permissions() -> None:
    """documents.read.All must not satisfy documents.write."""
    with pytest.raises(AuthorizationError):
        await _authorize({**_IDENTITY, "roles": ["documents.read.All"]}, Scopes.DOCUMENTS_WRITE)


@pytest.mark.unit
def test_unknown_requirement_maps_only_to_itself() -> None:
    """A requirement outside the model cannot be widened by accident."""
    assert accepted_literals("api.read") == {"api.read"}


@pytest.mark.unit
async def test_legacy_scope_literals_are_rejected() -> None:
    """The retired api.* model must not authorize anything."""
    with pytest.raises(AuthorizationError):
        await _authorize({**_IDENTITY, "roles": ["api.read", "api.admin"]}, Scopes.DOCUMENTS_READ)


@pytest.mark.unit
async def test_delegated_token_cannot_reach_a_route_it_lacks_scope_for() -> None:
    """Search-only callers must not gain the document-read surface."""
    with pytest.raises(AuthorizationError) as exc_info:
        await _authorize({**_IDENTITY, "scp": "Search"}, Scopes.DOCUMENTS_READ)

    assert Scopes.DOCUMENTS_READ in exc_info.value.required


@pytest.mark.unit
async def test_no_scope_implication_admin_does_not_grant_read() -> None:
    with pytest.raises(AuthorizationError):
        await _authorize({**_IDENTITY, "roles": ["admin"]}, Scopes.DOCUMENTS_READ)


@pytest.mark.unit
async def test_all_required_scopes_must_be_present() -> None:
    with pytest.raises(AuthorizationError):
        await _authorize(
            {**_IDENTITY, "roles": ["documents.read"]},
            Scopes.DOCUMENTS_READ,
            Scopes.DOCUMENTS_WRITE,
        )


# ---------------------------------------------------------------------------
# Identity claims — 401 rather than an unhandled KeyError -> 500
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("missing", ["oid", "tid"])
async def test_token_missing_identity_claim_raises_authentication_error(missing: str) -> None:
    claims = {**_IDENTITY, "roles": ["documents.read"]}
    del claims[missing]

    with pytest.raises(AuthenticationError, match="identity claims"):
        await _authorize(claims, Scopes.DOCUMENTS_READ)


@pytest.mark.unit
async def test_token_with_empty_identity_claim_raises_authentication_error() -> None:
    claims = {"oid": "", "tid": "tenant-guid", "roles": ["documents.read"]}

    with pytest.raises(AuthenticationError, match="identity claims"):
        await _authorize(claims, Scopes.DOCUMENTS_READ)


@pytest.mark.unit
async def test_identity_claims_are_checked_after_scope_check() -> None:
    """An unauthorized caller gets 403 regardless of claim completeness."""
    claims = {"roles": ["documents.read"]}  # no oid/tid at all

    with pytest.raises(AuthorizationError):
        await _authorize(claims, Scopes.ADMIN)
