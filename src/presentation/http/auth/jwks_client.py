"""Async JWKS client with TTL cache and stampede protection."""

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class JwksClient:
    """Fetches and caches JSON Web Key Sets from a JWKS URI.

    Keys are cached by kid in a dict. Refresh is triggered when:
    - The TTL has expired (default 1 hour).
    - A token presents a kid that is not in the cache (handles key rotation).

    An asyncio.Lock prevents concurrent callers from issuing multiple
    simultaneous refresh requests (stampede protection).
    """

    def __init__(self, jwks_uri: str, ttl_seconds: int = 3600) -> None:
        self._jwks_uri = jwks_uri
        self._ttl_seconds = ttl_seconds
        self._keys: dict[str, Any] = {}
        self._fetched_at: float = 0.0
        self._lock = asyncio.Lock()

    async def get_signing_key(self, kid: str) -> dict[str, Any]:
        """Return the JWK for the given kid, refreshing the cache if needed.

        Refresh is triggered when the TTL has expired (routine refresh) or
        when the kid is unknown (handles key rotation between TTL cycles).

        Args:
            kid: Key ID from the JWT header.

        Returns:
            JWK dict for the matching key.

        Raises:
            ValueError: If the kid is not found even after a forced refresh.
        """
        if self._is_stale():
            await self._refresh_keys(force=False)

        if kid not in self._keys:
            await self._refresh_keys(force=True)

        if kid not in self._keys:
            raise ValueError(f"Signing key not found for kid='{kid}'")

        return self._keys[kid]

    def _is_stale(self) -> bool:
        return (time.monotonic() - self._fetched_at) >= self._ttl_seconds

    async def _refresh_keys(self, force: bool = False) -> None:
        async with self._lock:
            # Re-check under lock — another coroutine may have refreshed already.
            # Skip only if not forced, TTL is still valid, and we have keys cached.
            if not force and not self._is_stale() and self._keys:
                return

            logger.info("Refreshing JWKS from %s", self._jwks_uri)
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self._jwks_uri)
                response.raise_for_status()
                data = response.json()

            self._keys = {key["kid"]: key for key in data.get("keys", [])}
            self._fetched_at = time.monotonic()
            logger.info("JWKS refreshed — %d keys cached", len(self._keys))

    async def close(self) -> None:
        """No persistent connection to close; present for resource lifecycle compatibility."""
