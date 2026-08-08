"""Fail-closed startup guard (AIA-482, implemented under AIA-675).

``ENTRA_ID_ENABLED`` defaults to false, and when auth is disabled every request
resolves to an anonymous user holding every scope. A deployment that forgets the
variable therefore serves the whole API unauthenticated with only a log warning
to show for it — which is exactly what happened to the dev Container App.

The guard turns that silent exposure into a startup failure.
"""

from unittest.mock import MagicMock

import pytest

from src.config.settings import EntraIDSettings, Settings
from src.main import AuthConfigurationError, verify_auth_configuration


def _settings(
    *,
    environment: str = "dev",
    enabled: bool = False,
    tenant_id: str = "",
    client_id: str = "",
    allow_anonymous: bool = False,
) -> MagicMock:
    """Build a settings double carrying real EntraIDSettings for the computed fields."""
    settings = MagicMock(spec=Settings)
    settings.entra_id = EntraIDSettings(
        enabled=enabled, tenant_id=tenant_id, client_id=client_id
    )
    settings.environment = environment
    settings.allow_anonymous_auth = allow_anonymous
    settings.is_development = environment.lower() in ("development", "dev", "local")
    settings.is_production = environment.lower() in ("production", "prod")
    return settings


# ---------------------------------------------------------------------------
# Auth disabled
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("environment", ["dev", "development", "local", "LOCAL"])
def test_disabled_auth_is_permitted_in_development(environment: str) -> None:
    verify_auth_configuration(_settings(environment=environment))  # must not raise


@pytest.mark.unit
@pytest.mark.parametrize("environment", ["test", "staging", "prod", "production"])
def test_disabled_auth_refuses_to_start_outside_development(environment: str) -> None:
    with pytest.raises(AuthConfigurationError, match="Authentication is disabled"):
        verify_auth_configuration(_settings(environment=environment))


@pytest.mark.unit
def test_explicit_escape_hatch_allows_disabled_auth_outside_development() -> None:
    verify_auth_configuration(_settings(environment="prod", allow_anonymous=True))


# ---------------------------------------------------------------------------
# Auth enabled
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_enabled_and_fully_configured_starts() -> None:
    verify_auth_configuration(
        _settings(environment="prod", enabled=True, tenant_id="tenant", client_id="client")
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("tenant_id", "client_id"),
    [("", "client"), ("tenant", ""), ("", "")],
)
def test_enabled_but_incomplete_configuration_refuses_to_start(
    tenant_id: str, client_id: str
) -> None:
    """Without both ids the validator cannot build issuer/JWKS/audience — every
    request would 401. Fail at startup rather than at request time."""
    with pytest.raises(AuthConfigurationError, match="not fully configured"):
        verify_auth_configuration(
            _settings(environment="prod", enabled=True, tenant_id=tenant_id, client_id=client_id)
        )


@pytest.mark.unit
def test_incomplete_configuration_fails_even_in_development() -> None:
    """A broken config is never useful — the dev allowance covers auth being off,
    not auth being on and unusable."""
    with pytest.raises(AuthConfigurationError, match="not fully configured"):
        verify_auth_configuration(_settings(environment="dev", enabled=True, tenant_id="tenant"))


# ---------------------------------------------------------------------------
# Audience resolution (the misconfiguration that silently 401s everything)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_both_audience_forms_are_accepted_by_default() -> None:
    settings = EntraIDSettings(enabled=True, tenant_id="tenant", client_id="client-guid")

    assert settings.accepted_audiences == ["api://client-guid", "client-guid"]


@pytest.mark.unit
def test_explicit_override_replaces_the_default_audiences() -> None:
    settings = EntraIDSettings(
        enabled=True, tenant_id="tenant", client_id="client-guid", audience="api://custom"
    )

    assert settings.accepted_audiences == ["api://custom"]


@pytest.mark.unit
def test_unconfigured_client_id_yields_no_accepted_audiences() -> None:
    """Guards against accepting a token whose aud is the empty string.

    client_id is passed explicitly: constructor arguments outrank the ambient
    environment and any local .env, keeping this assertion hermetic.
    """
    assert EntraIDSettings(enabled=False, tenant_id="", client_id="").accepted_audiences == []
