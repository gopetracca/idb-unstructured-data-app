"""Unit tests for TokenValidator."""

import time
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from jwt.algorithms import RSAAlgorithm

from src.config.settings import EntraIDSettings
from src.presentation.http.auth.errors import AuthenticationError
from src.presentation.http.auth.jwks_client import JwksClient
from src.presentation.http.auth.token_validator import TokenValidator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_rsa_key_pair():
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    return private_key, private_key.public_key()


def _make_token(
    private_key,
    kid: str = "test-kid",
    iss: str = "https://login.microsoftonline.com/test-tenant/v2.0",
    aud: str = "api://test-client-id",
    exp_delta: int = 3600,
    extra_claims: dict | None = None,
) -> str:
    payload = {
        "iss": iss,
        "aud": aud,
        "sub": "user-sub",
        "oid": "user-oid-123",
        "tid": "test-tenant",
        "preferred_username": "user@example.com",
        "roles": ["api.read"],
        "exp": int(time.time()) + exp_delta,
        "nbf": int(time.time()) - 10,
        "iat": int(time.time()) - 10,
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(
        payload,
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )


def _make_jwk(private_key, kid: str = "test-kid") -> dict:
    return {**RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True), "kid": kid}


def _make_settings(tenant_id: str = "test-tenant", client_id: str = "test-client-id") -> EntraIDSettings:
    return EntraIDSettings(
        enabled=True,
        tenant_id=tenant_id,
        client_id=client_id,
    )


def _make_validator(jwk: dict, kid: str = "test-kid") -> TokenValidator:
    jwks_client = MagicMock(spec=JwksClient)
    jwks_client.get_signing_key = AsyncMock(return_value=jwk)
    settings = _make_settings()
    return TokenValidator(jwks_client=jwks_client, settings=settings)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_valid_token_returns_claims() -> None:
    private_key, _ = _generate_rsa_key_pair()
    jwk = _make_jwk(private_key)
    validator = _make_validator(jwk)

    token = _make_token(private_key)
    claims = await validator.validate(token)

    assert claims["oid"] == "user-oid-123"
    assert claims["tid"] == "test-tenant"
    assert "api.read" in claims["roles"]


@pytest.mark.unit
async def test_expired_token_raises_authentication_error() -> None:
    private_key, _ = _generate_rsa_key_pair()
    jwk = _make_jwk(private_key)
    validator = _make_validator(jwk)

    token = _make_token(private_key, exp_delta=-60)  # expired beyond 30s leeway

    with pytest.raises(AuthenticationError, match="expired"):
        await validator.validate(token)


@pytest.mark.unit
async def test_wrong_audience_raises_authentication_error() -> None:
    private_key, _ = _generate_rsa_key_pair()
    jwk = _make_jwk(private_key)
    validator = _make_validator(jwk)

    token = _make_token(private_key, aud="api://wrong-audience")

    with pytest.raises(AuthenticationError, match="audience"):
        await validator.validate(token)


@pytest.mark.unit
async def test_wrong_issuer_raises_authentication_error() -> None:
    private_key, _ = _generate_rsa_key_pair()
    jwk = _make_jwk(private_key)
    validator = _make_validator(jwk)

    token = _make_token(private_key, iss="https://attacker.example.com/v2.0")

    with pytest.raises(AuthenticationError, match="issuer"):
        await validator.validate(token)


@pytest.mark.unit
async def test_malformed_token_raises_authentication_error() -> None:
    private_key, _ = _generate_rsa_key_pair()
    jwk = _make_jwk(private_key)
    validator = _make_validator(jwk)

    with pytest.raises(AuthenticationError, match="Malformed"):
        await validator.validate("not.a.valid.jwt.at.all")


@pytest.mark.unit
async def test_token_missing_kid_raises_authentication_error() -> None:
    private_key, _ = _generate_rsa_key_pair()
    jwk = _make_jwk(private_key)
    validator = _make_validator(jwk)

    # Sign without kid in header
    payload = {
        "iss": "https://login.microsoftonline.com/test-tenant/v2.0",
        "aud": "api://test-client-id",
        "oid": "user-oid",
        "tid": "test-tenant",
        "exp": int(time.time()) + 3600,
        "nbf": int(time.time()) - 10,
    }
    token = jwt.encode(payload, private_key, algorithm="RS256")  # no kid header

    with pytest.raises(AuthenticationError, match="kid"):
        await validator.validate(token)


@pytest.mark.unit
async def test_unknown_kid_raises_authentication_error() -> None:
    private_key, _ = _generate_rsa_key_pair()
    jwk = _make_jwk(private_key)

    jwks_client = MagicMock(spec=JwksClient)
    jwks_client.get_signing_key = AsyncMock(side_effect=ValueError("Signing key not found for kid='unknown'"))
    settings = _make_settings()
    validator = TokenValidator(jwks_client=jwks_client, settings=settings)

    token = _make_token(private_key, kid="unknown")

    with pytest.raises(AuthenticationError, match="Unknown signing key"):
        await validator.validate(token)


# ---------------------------------------------------------------------------
# Audience forms (AIA-675)
#
# Entra emits `aud` as the bare client ID for v2 tokens
# (requestedAccessTokenVersion: 2) and as the api:// identifier URI for v1.
# The real dev app registration is v2, so accepting only api://{client_id}
# rejected every token with "Invalid token audience".
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_bare_client_id_audience_is_accepted() -> None:
    """v2 token shape — this is what the live app registration issues."""
    private_key, _ = _generate_rsa_key_pair()
    validator = _make_validator(_make_jwk(private_key))

    token = _make_token(private_key, aud="test-client-id")
    claims = await validator.validate(token)

    assert claims["aud"] == "test-client-id"


@pytest.mark.unit
async def test_identifier_uri_audience_is_still_accepted() -> None:
    """v1 token shape — kept working so the setting is not version-sensitive."""
    private_key, _ = _generate_rsa_key_pair()
    validator = _make_validator(_make_jwk(private_key))

    token = _make_token(private_key, aud="api://test-client-id")
    claims = await validator.validate(token)

    assert claims["aud"] == "api://test-client-id"


@pytest.mark.unit
async def test_explicit_audience_override_narrows_accepted_values() -> None:
    """An explicit ENTRA_ID_AUDIENCE pins validation to exactly that value."""
    private_key, _ = _generate_rsa_key_pair()
    settings = EntraIDSettings(
        enabled=True,
        tenant_id="test-tenant",
        client_id="test-client-id",
        audience="api://custom-audience",
    )
    jwks_client = MagicMock(spec=JwksClient)
    jwks_client.get_signing_key = AsyncMock(return_value=_make_jwk(private_key))
    validator = TokenValidator(jwks_client=jwks_client, settings=settings)

    assert settings.accepted_audiences == ["api://custom-audience"]

    accepted = await validator.validate(_make_token(private_key, aud="api://custom-audience"))
    assert accepted["aud"] == "api://custom-audience"

    with pytest.raises(AuthenticationError, match="audience"):
        await validator.validate(_make_token(private_key, aud="test-client-id"))


# ---------------------------------------------------------------------------
# Calling-application allowlist (AIA-675)
# ---------------------------------------------------------------------------


def _validator_with_allowlist(private_key, allowed: list[str]) -> TokenValidator:
    settings = EntraIDSettings(
        enabled=True,
        tenant_id="test-tenant",
        client_id="test-client-id",
        allowed_client_ids=allowed,
    )
    jwks_client = MagicMock(spec=JwksClient)
    jwks_client.get_signing_key = AsyncMock(return_value=_make_jwk(private_key))
    return TokenValidator(jwks_client=jwks_client, settings=settings)


@pytest.mark.unit
async def test_allowlisted_client_is_accepted() -> None:
    private_key, _ = _generate_rsa_key_pair()
    validator = _validator_with_allowlist(private_key, ["allowed-app"])

    token = _make_token(private_key, extra_claims={"azp": "allowed-app"})
    claims = await validator.validate(token)

    assert claims["azp"] == "allowed-app"


@pytest.mark.unit
async def test_non_allowlisted_client_is_rejected() -> None:
    private_key, _ = _generate_rsa_key_pair()
    validator = _validator_with_allowlist(private_key, ["allowed-app"])

    token = _make_token(private_key, extra_claims={"azp": "some-other-app"})

    with pytest.raises(AuthenticationError, match="not allowed"):
        await validator.validate(token)


@pytest.mark.unit
async def test_appid_claim_is_honoured_when_azp_absent() -> None:
    """v1-style tokens carry appid rather than azp."""
    private_key, _ = _generate_rsa_key_pair()
    validator = _validator_with_allowlist(private_key, ["allowed-app"])

    token = _make_token(private_key, extra_claims={"appid": "allowed-app"})
    claims = await validator.validate(token)

    assert claims["appid"] == "allowed-app"


@pytest.mark.unit
async def test_empty_allowlist_accepts_any_valid_caller() -> None:
    private_key, _ = _generate_rsa_key_pair()
    validator = _make_validator(_make_jwk(private_key))  # no allowlist configured

    token = _make_token(private_key, extra_claims={"azp": "anything-at-all"})
    claims = await validator.validate(token)

    assert claims["azp"] == "anything-at-all"
