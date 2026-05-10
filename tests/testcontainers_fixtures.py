"""Session-scoped testcontainers fixtures for SQL Server and Azurite.

These fixtures manage container lifecycles automatically so that integration
tests are self-contained — no manual ``docker compose up`` required.

Usage:
    Register via ``pytest_plugins = ["tests.testcontainers_fixtures"]``
    in ``tests/conftest.py`` (already done).
"""

from __future__ import annotations

import pyodbc
import pytest
from alembic import command
from alembic.config import Config
from pathlib import Path
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.mssql import SqlServerContainer

from src.config.settings import AzureStorageSettings
from src.infrastructure.azure.clients.blob_client import BlobStorageClient
from src.infrastructure.azure.clients.queue_client import QueueStorageClient

_MSSQL_IMAGE = "mcr.microsoft.com/mssql/server:2022-latest"
_MSSQL_SA_PASSWORD = "YourStrong!Passw0rd"
_MSSQL_TEST_DATABASE = "db-np-d-aimvp-test"
_MSSQL_DRIVER = "ODBC+Driver+18+for+SQL+Server"

_AZURITE_IMAGE = "mcr.microsoft.com/azure-storage/azurite"
_AZURITE_ACCOUNT_NAME = "devstoreaccount1"
_AZURITE_ACCOUNT_KEY = (
    "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/"
    "K1SZFPTOtr/KBHBeksoGMGw=="
)


# ---------------------------------------------------------------------------
# SQL Server
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def sqlserver_container():
    """Start a SQL Server container for the entire test session.

    Creates the ``db-np-d-aimvp-test`` database and runs Alembic migrations
    before yielding so all session-sharing fixtures see a fully migrated schema.
    """
    with SqlServerContainer(
        image=_MSSQL_IMAGE,
        password=_MSSQL_SA_PASSWORD,
    ) as container:
        mapped_port = container.get_exposed_port(1433)
        _create_test_database(mapped_port)
        _run_alembic_migrations(mapped_port)
        yield container


def _create_test_database(mapped_port: int) -> None:
    """Create the test database inside the running container via pyodbc."""
    master_url = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER=127.0.0.1,{mapped_port};"
        f"DATABASE=master;"
        f"UID=sa;"
        f"PWD={_MSSQL_SA_PASSWORD};"
        f"TrustServerCertificate=yes;"
    )
    conn = pyodbc.connect(master_url, autocommit=True)
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = '{_MSSQL_TEST_DATABASE}')"
            f" CREATE DATABASE [{_MSSQL_TEST_DATABASE}]"
        )
    finally:
        conn.close()


def _run_alembic_migrations(mapped_port: int) -> None:
    """Run Alembic migrations programmatically against the test database."""
    async_url = (
        f"mssql+aioodbc://sa:{_MSSQL_SA_PASSWORD}@127.0.0.1:{mapped_port}"
        f"/{_MSSQL_TEST_DATABASE}"
        f"?driver={_MSSQL_DRIVER}&TrustServerCertificate=yes"
    )
    alembic_ini = Path(__file__).parent.parent / "alembic.ini"
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("sqlalchemy.url", async_url)
    command.upgrade(cfg, "head")


def _build_async_db_url(mapped_port: int) -> str:
    return (
        f"mssql+aioodbc://sa:{_MSSQL_SA_PASSWORD}@127.0.0.1:{mapped_port}"
        f"/{_MSSQL_TEST_DATABASE}"
        f"?driver={_MSSQL_DRIVER}&TrustServerCertificate=yes"
    )


@pytest.fixture(scope="session")
def sqlserver_engine(sqlserver_container: SqlServerContainer):
    """Async SQLAlchemy engine connected to the testcontainer SQL Server.

    Uses NullPool so connections are never cached across async event loops.
    Each test gets a fresh connection that is closed immediately after use,
    which avoids ``RuntimeError: Event loop is closed`` teardown errors when
    pytest-asyncio creates a new event loop per test function.

    Synchronous fixture so it can be session-scoped without requiring a
    session-scoped event loop.
    """
    mapped_port = sqlserver_container.get_exposed_port(1433)
    url = _build_async_db_url(mapped_port)
    engine = create_async_engine(url, echo=False, poolclass=NullPool)
    yield engine
    engine.sync_engine.dispose()


@pytest.fixture(scope="session")
def sqlserver_session_factory(sqlserver_engine) -> async_sessionmaker[AsyncSession]:
    """Async session factory bound to the testcontainer SQL Server engine."""
    return async_sessionmaker(
        bind=sqlserver_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


# ---------------------------------------------------------------------------
# Azurite
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def azurite_container():
    """Start an Azurite container for the entire test session.

    Initialises blob containers and queues via the existing storage clients
    so tests can rely on the standard resource names from AzureStorageSettings.
    """
    container = (
        DockerContainer(_AZURITE_IMAGE)
        .with_exposed_ports(10000, 10001, 10002)
        .with_command(
            "azurite "
            "--blobHost 0.0.0.0 "
            "--queueHost 0.0.0.0 "
            "--tableHost 0.0.0.0 "
            "--loose "
            "--skipApiVersionCheck"
        )
    )
    with container:
        wait_for_logs(container, "Azurite Queue service is successfully listening")
        conn_str = _build_azurite_connection_string(container)
        _init_storage_resources(conn_str)
        yield container


def _build_azurite_connection_string(container: DockerContainer) -> str:
    blob_port = container.get_exposed_port(10000)
    queue_port = container.get_exposed_port(10001)
    table_port = container.get_exposed_port(10002)
    return (
        f"DefaultEndpointsProtocol=http;"
        f"AccountName={_AZURITE_ACCOUNT_NAME};"
        f"AccountKey={_AZURITE_ACCOUNT_KEY};"
        f"BlobEndpoint=http://127.0.0.1:{blob_port}/{_AZURITE_ACCOUNT_NAME};"
        f"QueueEndpoint=http://127.0.0.1:{queue_port}/{_AZURITE_ACCOUNT_NAME};"
        f"TableEndpoint=http://127.0.0.1:{table_port}/{_AZURITE_ACCOUNT_NAME}"
    )


def _init_storage_resources(conn_str: str) -> None:
    """Create all blob containers and queues expected by AzureStorageSettings defaults."""
    settings = AzureStorageSettings(connection_string=conn_str)
    blob_client = BlobStorageClient(settings)
    queue_client = QueueStorageClient(settings)
    for container_name in settings.container_names:
        blob_client.create_container_if_not_exists_sync(container_name)
    for queue_name in settings.queue_names:
        queue_client.create_queue_if_not_exists_sync(queue_name)


@pytest.fixture(scope="session")
def azurite_connection_string(azurite_container: DockerContainer) -> str:
    """Dynamic Azurite connection string built from testcontainer mapped ports."""
    return _build_azurite_connection_string(azurite_container)


@pytest.fixture(scope="session")
def azurite_storage_settings(azurite_connection_string: str) -> AzureStorageSettings:
    """AzureStorageSettings configured to point at the testcontainer Azurite instance."""
    return AzureStorageSettings(connection_string=azurite_connection_string)
