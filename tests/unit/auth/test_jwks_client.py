"""Unit tests for JwksClient."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.presentation.http.auth.jwks_client import JwksClient

MOCK_JWKS = {
    "keys": [
        {"kid": "key-1", "kty": "RSA", "n": "abc", "e": "AQAB"},
        {"kid": "key-2", "kty": "RSA", "n": "def", "e": "AQAB"},
    ]
}


def _make_mock_response(json_data: dict) -> MagicMock:
    response = MagicMock()
    response.json.return_value = json_data
    response.raise_for_status = MagicMock()
    return response


@pytest.fixture
def client() -> JwksClient:
    return JwksClient(jwks_uri="https://example.com/keys", ttl_seconds=3600)


@pytest.mark.unit
async def test_get_signing_key_fetches_on_first_call(client: JwksClient) -> None:
    mock_response = _make_mock_response(MOCK_JWKS)

    with patch("httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_http.return_value)
        mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.return_value.get = AsyncMock(return_value=mock_response)

        key = await client.get_signing_key("key-1")

    assert key["kid"] == "key-1"


@pytest.mark.unit
async def test_get_signing_key_uses_cache_on_second_call(client: JwksClient) -> None:
    mock_response = _make_mock_response(MOCK_JWKS)

    with patch("httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_http.return_value)
        mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.return_value.get = AsyncMock(return_value=mock_response)

        await client.get_signing_key("key-1")
        await client.get_signing_key("key-2")

        # Only one HTTP call despite two key lookups
        assert mock_http.return_value.get.call_count == 1


@pytest.mark.unit
async def test_get_signing_key_refreshes_on_ttl_expiry(client: JwksClient) -> None:
    mock_response = _make_mock_response(MOCK_JWKS)

    with patch("httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_http.return_value)
        mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.return_value.get = AsyncMock(return_value=mock_response)

        await client.get_signing_key("key-1")

        # Simulate TTL expiry
        client._fetched_at = time.monotonic() - 7200

        await client.get_signing_key("key-1")

        assert mock_http.return_value.get.call_count == 2


@pytest.mark.unit
async def test_get_signing_key_refreshes_on_unknown_kid() -> None:
    """An unknown kid forces a refresh when the throttle is not in the way.

    The throttle itself (added in AIA-675) is covered separately below; here it
    is disabled so this test keeps asserting only the key-rotation behaviour.
    """
    client = JwksClient(
        jwks_uri="https://example.com/keys",
        ttl_seconds=3600,
        force_refresh_min_interval_seconds=0,
    )
    initial_jwks = {"keys": [{"kid": "old-key", "kty": "RSA", "n": "abc", "e": "AQAB"}]}
    updated_jwks = {
        "keys": [
            {"kid": "old-key", "kty": "RSA", "n": "abc", "e": "AQAB"},
            {"kid": "new-key", "kty": "RSA", "n": "xyz", "e": "AQAB"},
        ]
    }

    with patch("httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_http.return_value)
        mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.return_value.get = AsyncMock(
            side_effect=[
                _make_mock_response(initial_jwks),
                _make_mock_response(updated_jwks),
            ]
        )

        await client.get_signing_key("old-key")
        key = await client.get_signing_key("new-key")  # triggers refresh

    assert key["kid"] == "new-key"
    assert mock_http.return_value.get.call_count == 2


@pytest.mark.unit
async def test_get_signing_key_raises_if_kid_not_found_after_refresh(client: JwksClient) -> None:
    mock_response = _make_mock_response(MOCK_JWKS)

    with patch("httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_http.return_value)
        mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.return_value.get = AsyncMock(return_value=mock_response)

        with pytest.raises(ValueError, match="Signing key not found"):
            await client.get_signing_key("non-existent-kid")


# ---------------------------------------------------------------------------
# Forced-refresh throttle (AIA-675)
#
# An unknown kid forces a JWKS fetch. Unthrottled, a flood of tokens carrying
# bogus kids turns cheap unauthenticated requests into one outbound fetch each
# — DoS amplification against this service and against Entra.
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_repeated_unknown_kids_do_not_each_force_a_refresh() -> None:
    throttled = JwksClient(
        jwks_uri="https://example.com/keys",
        ttl_seconds=3600,
        force_refresh_min_interval_seconds=60,
    )
    mock_response = _make_mock_response(MOCK_JWKS)

    with patch("httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_http.return_value)
        mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.return_value.get = AsyncMock(return_value=mock_response)

        for index in range(25):
            with pytest.raises(ValueError):
                await throttled.get_signing_key(f"bogus-kid-{index}")

        # A single cold-start fetch serves all 25 bogus kids. Without the
        # throttle this would be 25+ outbound requests.
        assert mock_http.return_value.get.call_count == 1


@pytest.mark.unit
async def test_forced_refresh_is_allowed_again_after_the_interval() -> None:
    """Genuine key rotation must still be picked up once the throttle expires."""
    throttled = JwksClient(
        jwks_uri="https://example.com/keys",
        ttl_seconds=3600,
        force_refresh_min_interval_seconds=60,
    )
    initial_jwks = {"keys": [{"kid": "old-key", "kty": "RSA", "n": "abc", "e": "AQAB"}]}
    rotated_jwks = {"keys": [{"kid": "rotated-key", "kty": "RSA", "n": "xyz", "e": "AQAB"}]}

    with patch("httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_http.return_value)
        mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.return_value.get = AsyncMock(
            side_effect=[
                _make_mock_response(initial_jwks),
                _make_mock_response(rotated_jwks),
            ]
        )

        await throttled.get_signing_key("old-key")

        # Throttled: the rotated key is not visible yet.
        with pytest.raises(ValueError):
            await throttled.get_signing_key("rotated-key")

        # Advance past the throttle window (both stamps age as real time passes,
        # but 120s stays well inside the 3600s TTL so this is the forced path).
        throttled._forced_at = time.monotonic() - 120
        throttled._fetched_at = time.monotonic() - 120

        key = await throttled.get_signing_key("rotated-key")

    assert key["kid"] == "rotated-key"


@pytest.mark.unit
async def test_ttl_refresh_is_not_blocked_by_the_force_throttle() -> None:
    """The throttle governs forced refreshes only; routine TTL refresh is unaffected."""
    throttled = JwksClient(
        jwks_uri="https://example.com/keys",
        ttl_seconds=3600,
        force_refresh_min_interval_seconds=3600,
    )
    mock_response = _make_mock_response(MOCK_JWKS)

    with patch("httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_http.return_value)
        mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.return_value.get = AsyncMock(return_value=mock_response)

        await throttled.get_signing_key("key-1")
        throttled._fetched_at = time.monotonic() - 7200  # TTL expired
        await throttled.get_signing_key("key-1")

        assert mock_http.return_value.get.call_count == 2
