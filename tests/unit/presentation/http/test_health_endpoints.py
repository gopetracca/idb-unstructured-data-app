"""Health probe tests (AIA-479)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.container import Container
from src.main import app

pytestmark = pytest.mark.unit


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _healthy_search() -> MagicMock:
    adapter = MagicMock()
    adapter.health_check = AsyncMock(return_value=True)
    return adapter


def _failing_search() -> MagicMock:
    adapter = MagicMock()
    adapter.health_check = AsyncMock(return_value=False)
    return adapter


class TestLiveness:
    def test_live_returns_200_without_touching_dependencies(self, client: TestClient) -> None:
        """Liveness must not construct or call any dependency."""
        container = Container()
        exploding = MagicMock()
        exploding.health_check = AsyncMock(side_effect=AssertionError("liveness touched a dependency"))
        with container.vector_database_adapter.override(exploding):
            response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"
        exploding.health_check.assert_not_awaited()

    def test_root_still_serves_as_liveness_alias(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestReadiness:
    def test_ready_when_all_dependencies_pass(self, client: TestClient) -> None:
        container = Container()
        with (
            container.sql_session_factory.override(None),
            container.vector_database_adapter.override(_healthy_search()),
        ):
            response = client.get("/health/ready")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert body["checks"]["search"] == "ok"
        assert body["checks"]["sql"] == "disabled"

    def test_returns_503_when_search_unreachable(self, client: TestClient) -> None:
        container = Container()
        with (
            container.sql_session_factory.override(None),
            container.vector_database_adapter.override(_failing_search()),
        ):
            response = client.get("/health/ready")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "not_ready"
        assert body["checks"]["search"].startswith("error")

    def test_returns_503_when_sql_check_raises(self, client: TestClient) -> None:
        failing_factory = MagicMock(side_effect=ConnectionError("db down"))
        container = Container()
        with (
            container.sql_session_factory.override(failing_factory),
            container.vector_database_adapter.override(_healthy_search()),
        ):
            response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["checks"]["sql"].startswith("error")
