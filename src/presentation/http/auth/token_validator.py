"""JWT token validator for Microsoft Entra ID bearer tokens."""

import logging
from typing import Any

import jwt
from jwt.algorithms import RSAAlgorithm

from src.config.settings import EntraIDSettings
from src.presentation.http.auth.errors import AuthenticationError
from src.presentation.http.auth.jwks_client import JwksClient

logger = logging.getLogger(__name__)

# Allow 30-second clock skew between issuer and this service.
_LEEWAY_SECONDS = 30


class TokenValidator:
    """Validates RS256 JWT bearer tokens issued by Microsoft Entra ID.

    Performs full validation:
    - Decodes the JWT header to extract the kid.
    - Fetches the matching public key from the JWKS endpoint.
    - Verifies the RS256 signature.
    - Validates iss, aud, exp, and nbf claims (with configurable leeway).
    """

    def __init__(self, jwks_client: JwksClient, settings: EntraIDSettings) -> None:
        self._jwks_client = jwks_client
        self._settings = settings

    async def validate(self, token: str) -> dict[str, Any]:
        """Validate a bearer token and return its claims.

        Args:
            token: Raw JWT string (without the 'Bearer ' prefix).

        Returns:
            Decoded claims dict.

        Raises:
            AuthenticationError: If the token is invalid, expired, or cannot be verified.
        """
        try:
            header = jwt.get_unverified_header(token)
        except jwt.exceptions.DecodeError as exc:
            raise AuthenticationError("Malformed token header") from exc

        kid = header.get("kid")
        if not kid:
            raise AuthenticationError("Token header missing kid")

        try:
            jwk = await self._jwks_client.get_signing_key(kid)
        except ValueError as exc:
            raise AuthenticationError(f"Unknown signing key: {kid}") from exc
        except Exception as exc:
            logger.exception("Failed to fetch JWKS")
            raise AuthenticationError("Unable to retrieve signing keys") from exc

        public_key = RSAAlgorithm.from_jwk(jwk)

        try:
            claims = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                # A list: v2 tokens carry the bare client ID, v1 the api:// URI.
                audience=self._settings.accepted_audiences,
                issuer=self._settings.issuer,
                leeway=_LEEWAY_SECONDS,
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationError("Token has expired") from exc
        except jwt.InvalidAudienceError as exc:
            raise AuthenticationError("Invalid token audience") from exc
        except jwt.InvalidIssuerError as exc:
            raise AuthenticationError("Invalid token issuer") from exc
        except jwt.exceptions.PyJWTError as exc:
            raise AuthenticationError(f"Token validation failed: {exc}") from exc

        self._assert_client_allowed(claims)
        return claims

    def _assert_client_allowed(self, claims: dict[str, Any]) -> None:
        """Enforce the optional calling-application allowlist.

        Defense in depth for M2M: a valid token for this audience proves the
        caller holds *a* client credential in the tenant, not that it is one of
        the applications we expect. When ENTRA_ID_ALLOWED_CLIENT_IDS is empty
        the check is skipped and any valid-audience caller is accepted.
        """
        allowed = self._settings.allowed_client_ids
        if not allowed:
            return

        caller = claims.get("azp") or claims.get("appid")
        if caller not in allowed:
            logger.warning("Rejected token from non-allowlisted client application: %s", caller)
            raise AuthenticationError("Calling application is not allowed")
