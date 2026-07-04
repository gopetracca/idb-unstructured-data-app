"""Upload size-limit tests (AIA-478).

Exercise the layered defense end-to-end through the ASGI stack:
- Content-Length pre-check → immediate 413, body never read.
- Streaming counter → 413 for chunked/understated bodies.
- Boundary: a file exactly at the configured limit is accepted.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.application.dto.document_dto import UploadDocumentOutput
from src.application.use_cases.upload_and_enqueue_document import (
    UploadAndEnqueueDocumentUseCase,
)
from src.config.settings import get_settings
from src.container import Container
from src.core.value_objects.document_metadata import DocumentMetadata
from src.main import app
from src.presentation.http.auth import CurrentUser, get_current_user
from src.presentation.http.middleware.max_body_size import MULTIPART_OVERHEAD_BYTES

pytestmark = pytest.mark.unit


def _make_user() -> CurrentUser:
    return CurrentUser(
        user_id="test-user",
        tenant_id="test-tenant",
        email="test@example.com",
        roles=["documents.write"],
    )


def _mock_use_case() -> MagicMock:
    use_case = MagicMock(spec=UploadAndEnqueueDocumentUseCase)
    use_case.execute = AsyncMock(
        return_value=UploadDocumentOutput(
            file_id="file-abc-123",
            filename="test.pdf",
            size_bytes=1024,
            mime_type="application/pdf",
            uploaded_at=datetime(2026, 1, 28, 10, 0, 0),
            metadata=DocumentMetadata(file_id="file-abc-123", document_type="operational"),
        )
    )
    return use_case


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client(clear_overrides) -> TestClient:
    async def _auth_override():
        return _make_user()

    app.dependency_overrides[get_current_user] = _auth_override
    return TestClient(app, raise_server_exceptions=False)


def _upload(client: TestClient, payload: bytes, headers: dict | None = None):
    return client.post(
        "/api/v1/documents/operational",
        data={"collection_name": "ops", "ezshare_id": "EZ-LIMIT-001"},
        files={"file": ("big.pdf", payload, "application/pdf")},
        headers=headers or {},
    )


def test_oversized_content_length_is_rejected_immediately(client: TestClient) -> None:
    """A request declaring an oversized Content-Length gets 413 without upload processing."""
    limit = get_settings().file_upload.max_file_size_bytes
    response = client.post(
        "/api/v1/documents/operational",
        content=b"",
        headers={
            "Content-Length": str(limit + MULTIPART_OVERHEAD_BYTES + 1),
            "Content-Type": "multipart/form-data; boundary=x",
        },
    )
    assert response.status_code == 413
    assert response.json()["error"] == "FileSizeExceeded"


def test_oversized_streamed_body_is_rejected(client: TestClient) -> None:
    """A body that exceeds the limit is aborted by the streaming guard with 413."""
    limit = get_settings().file_upload.max_file_size_bytes
    oversized = b"x" * (limit + MULTIPART_OVERHEAD_BYTES + 1)
    response = _upload(client, oversized)
    assert response.status_code == 413
    assert response.json()["error"] == "FileSizeExceeded"


def test_file_over_limit_but_under_overhead_is_rejected_by_route_guard(
    client: TestClient,
) -> None:
    """A file just over the file limit (within the multipart overhead headroom)
    passes the middleware but is rejected by the bounded route-level read.

    The use-case provider is overridden so the test isolates the route guard:
    if the guard failed to raise, the mocked use case would return 201.
    """
    limit = get_settings().file_upload.max_file_size_bytes
    container = Container()
    with container.upload_and_enqueue_document_use_case.override(_mock_use_case()):
        response = _upload(client, b"x" * (limit + 1))
    assert response.status_code == 413
    assert response.json()["error"] == "FileSizeExceeded"


def test_file_exactly_at_limit_is_accepted(client: TestClient) -> None:
    """Boundary: a file of exactly max_file_size_bytes still succeeds."""
    limit = get_settings().file_upload.max_file_size_bytes
    container = Container()
    with container.upload_and_enqueue_document_use_case.override(_mock_use_case()):
        response = _upload(client, b"x" * limit)
    assert response.status_code == 201


def test_valid_small_upload_still_succeeds(client: TestClient) -> None:
    container = Container()
    with container.upload_and_enqueue_document_use_case.override(_mock_use_case()):
        response = _upload(client, b"small pdf content")
    assert response.status_code == 201
    assert response.json()["file_id"] == "file-abc-123"
