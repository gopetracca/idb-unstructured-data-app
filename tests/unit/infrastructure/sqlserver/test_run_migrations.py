"""Unit tests for the database migration runner (AIA-394)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config.settings import SqlServerSettings
from src.infrastructure.sqlserver import run_migrations


def _settings(sql: SqlServerSettings) -> MagicMock:
    return MagicMock(sql_server=sql)


@pytest.mark.unit
def test_finds_alembic_ini_at_repo_root() -> None:
    ini = run_migrations._find_alembic_ini()
    assert ini.name == "alembic.ini"
    assert Path(ini).exists()


@pytest.mark.unit
async def test_skips_when_sql_server_disabled() -> None:
    disabled = SqlServerSettings(enabled=False)
    with patch.object(run_migrations, "get_settings", return_value=_settings(disabled)):
        await run_migrations._run()  # must not raise or attempt a connection


@pytest.mark.unit
async def test_fails_fast_when_enabled_without_url() -> None:
    enabled_without_url = SqlServerSettings(
        enabled=True, database_url="", database_url_migrations=""
    )
    with patch.object(
        run_migrations, "get_settings", return_value=_settings(enabled_without_url)
    ):
        with pytest.raises(RuntimeError, match="must be set"):
            await run_migrations._run()


@pytest.mark.unit
def test_main_returns_nonzero_on_failure() -> None:
    enabled_without_url = SqlServerSettings(
        enabled=True, database_url="", database_url_migrations=""
    )
    with patch.object(
        run_migrations, "get_settings", return_value=_settings(enabled_without_url)
    ):
        assert run_migrations.main() == 1


@pytest.mark.unit
def test_main_returns_zero_when_disabled() -> None:
    disabled = SqlServerSettings(enabled=False)
    with patch.object(run_migrations, "get_settings", return_value=_settings(disabled)):
        assert run_migrations.main() == 0
