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
async def test_get_signing_key_refreshes_on_unknown_kid(client: JwksClient) -> None:
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
