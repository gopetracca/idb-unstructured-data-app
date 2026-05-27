"""Integration tests for document upload HTTP endpoints.

Tests the generic POST /api/v1/documents endpoint (with document_type validation)
and the type-specific endpoints:
  - POST /api/v1/documents/operational
  - POST /api/v1/documents/publication
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.application.dto.document_dto import UploadDocumentOutput
from src.application.use_cases.upload_and_enqueue_document import (
    UploadAndEnqueueDocumentUseCase,
)
from src.container import Container
from src.core.value_objects.document_metadata import DocumentMetadata
from src.main import app
from src.presentation.http.auth import CurrentUser, get_current_user


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_user() -> CurrentUser:
    return CurrentUser(
        user_id="test-user",
        tenant_id="test-tenant",
        email="test@example.com",
        roles=["api.write"],
    )


def _make_upload_output() -> UploadDocumentOutput:
    return UploadDocumentOutput(
        file_id="file-abc-123",
        filename="test.pdf",
        size_bytes=1024,
        mime_type="application/pdf",
        uploaded_at=datetime(2026, 1, 28, 10, 0, 0),
        metadata=DocumentMetadata(file_id="file-abc-123", document_type="operational"),
    )


def _mock_use_case() -> MagicMock:
    use_case = MagicMock(spec=UploadAndEnqueueDocumentUseCase)
    use_case.execute = AsyncMock(return_value=_make_upload_output())
    return use_case


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_overrides():
    """Clean up dependency overrides after each test."""
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client_with_auth(clear_overrides) -> TestClient:
    """TestClient with auth bypassed via dependency override."""
    user = _make_user()

    async def _auth_override():
        return user

    app.dependency_overrides[get_current_user] = _auth_override
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def mock_use_case() -> MagicMock:
    return _mock_use_case()


# ---------------------------------------------------------------------------
# Generic endpoint — POST /api/v1/documents
# ---------------------------------------------------------------------------


class TestGenericUploadEndpoint:
    """Tests for the generic POST /api/v1/documents endpoint."""

    def test_rejects_unknown_document_type(self, client_with_auth: TestClient) -> None:
        """400 is returned when an unknown document_type is provided."""
        response = client_with_auth.post(
            "/api/v1/documents",
            data={
                "collection_name": "test",
                "ezshare_id": "EZ-001",
                "document_type": "unknown_type",
            },
            files={"file": ("test.pdf", b"pdf content", "application/pdf")},
        )
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["error"] == "InvalidDocumentType"
        assert "unknown_type" in detail["message"]

    def test_rejects_invalid_metadata_json(self, client_with_auth: TestClient) -> None:
        """400 is returned when metadata is not valid JSON."""
        response = client_with_auth.post(
            "/api/v1/documents",
            data={
                "collection_name": "test",
                "ezshare_id": "EZ-001",
                "document_type": "operational",
                "metadata": "{not valid json}",
            },
            files={"file": ("test.pdf", b"pdf content", "application/pdf")},
        )
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["error"] == "InvalidMetadataJSON"

    def test_rejects_metadata_with_invalid_field_values(
        self, client_with_auth: TestClient
    ) -> None:
        """400 is returned when metadata fields fail schema validation."""
        import json

        response = client_with_auth.post(
            "/api/v1/documents",
            data={
                "collection_name": "test",
                "ezshare_id": "EZ-001",
                "document_type": "operational",
                "metadata": json.dumps({"year": 3000}),  # year > 2100
            },
            files={"file": ("test.pdf", b"pdf content", "application/pdf")},
        )
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["error"] == "InvalidMetadata"
        assert "details" in detail

    def test_accepts_valid_operational_metadata(
        self, client_with_auth: TestClient, mock_use_case: MagicMock
    ) -> None:
        """201 is returned when a valid operational document is uploaded."""
        import json

        container = Container()
        with container.upload_and_enqueue_document_use_case.override(mock_use_case):
            response = client_with_auth.post(
                "/api/v1/documents",
                data={
                    "collection_name": "ops",
                    "ezshare_id": "EZ-001",
                    "document_type": "operational",
                    "metadata": json.dumps(
                        {"operation_number": "UR-P1180", "sector": "TRANSPORT", "year": 2024}
                    ),
                },
                files={"file": ("test.pdf", b"pdf content", "application/pdf")},
            )
        assert response.status_code == 201
        data = response.json()
        assert data["file_id"] == "file-abc-123"

    def test_accepts_valid_publication_metadata(
        self, client_with_auth: TestClient, mock_use_case: MagicMock
    ) -> None:
        """201 is returned when a valid publication document is uploaded."""
        import json

        mock_use_case.execute = AsyncMock(
            return_value=UploadDocumentOutput(
                file_id="file-pub-456",
                filename="paper.pdf",
                size_bytes=2048,
                mime_type="application/pdf",
                uploaded_at=datetime(2026, 1, 28, 10, 0, 0),
                metadata=DocumentMetadata(file_id="file-pub-456", document_type="publication"),
            )
        )
        container = Container()
        with container.upload_and_enqueue_document_use_case.override(mock_use_case):
            response = client_with_auth.post(
                "/api/v1/documents",
                data={
                    "collection_name": "publications",
                    "ezshare_id": "EZ-002",
                    "document_type": "publication",
                    "metadata": json.dumps(
                        {"journal": "Nature", "doi": "10.1234/example", "peer_reviewed": True}
                    ),
                },
                files={"file": ("paper.pdf", b"pdf content", "application/pdf")},
            )
        assert response.status_code == 201
        data = response.json()
        assert data["file_id"] == "file-pub-456"

    def test_defaults_to_operational_when_no_document_type(
        self, client_with_auth: TestClient, mock_use_case: MagicMock
    ) -> None:
        """When document_type is omitted the server injects document_category='operational'."""
        container = Container()
        with container.upload_and_enqueue_document_use_case.override(mock_use_case):
            response = client_with_auth.post(
                "/api/v1/documents",
                data={
                    "collection_name": "ops",
                    "ezshare_id": "EZ-003",
                },
                files={"file": ("doc.pdf", b"pdf content", "application/pdf")},
            )
        assert response.status_code == 201
        # Verify document_category was injected server-side as 'operational'
        call_args = mock_use_case.execute.call_args[0][0]
        assert call_args.metadata.get("document_category") == "operational"


# ---------------------------------------------------------------------------
# Operational endpoint — POST /api/v1/documents/operational
# ---------------------------------------------------------------------------


class TestOperationalUploadEndpoint:
    """Tests for POST /api/v1/documents/operational."""

    def test_upload_with_minimal_fields(
        self, client_with_auth: TestClient, mock_use_case: MagicMock
    ) -> None:
        """201 is returned with just the required fields."""
        container = Container()
        with container.upload_and_enqueue_document_use_case.override(mock_use_case):
            response = client_with_auth.post(
                "/api/v1/documents/operational",
                data={
                    "collection_name": "ops",
                    "ezshare_id": "EZ-100",
                },
                files={"file": ("doc.pdf", b"pdf content", "application/pdf")},
            )
        assert response.status_code == 201
        data = response.json()
        assert data["file_id"] == "file-abc-123"

    def test_upload_with_all_operational_fields(
        self, client_with_auth: TestClient, mock_use_case: MagicMock
    ) -> None:
        """201 is returned with full operational metadata."""
        container = Container()
        with container.upload_and_enqueue_document_use_case.override(mock_use_case):
            response = client_with_auth.post(
                "/api/v1/documents/operational",
                data={
                    "collection_name": "ops",
                    "ezshare_id": "EZ-101",
                    "operation_number": "UR-P1180",
                    "sector": "TRANSPORT",
                    "operation_type": "Loan",
                    "dept_id": "INE/TSP",
                    "country": "Uruguay",
                    "year": "2024",
                    "language": "en",
                    "document_name": "Annual Report",
                    "tags": "transport,infrastructure,2024",
                },
                files={"file": ("doc.pdf", b"pdf content", "application/pdf")},
            )
        assert response.status_code == 201
        # Verify metadata was forwarded correctly
        call_args = mock_use_case.execute.call_args[0][0]
        assert call_args.metadata.get("document_category") == "operational"
        assert call_args.metadata.get("operation_number") == "UR-P1180"
        assert call_args.metadata.get("sector") == "TRANSPORT"

    def test_rejects_missing_required_fields(self, client_with_auth: TestClient) -> None:
        """422 is returned when collection_name or ezshare_id is missing."""
        response = client_with_auth.post(
            "/api/v1/documents/operational",
            data={"operation_number": "UR-P1180"},
            files={"file": ("doc.pdf", b"pdf content", "application/pdf")},
        )
        assert response.status_code == 422

    def test_rejects_invalid_year_value(
        self, client_with_auth: TestClient
    ) -> None:
        """422 is returned when year is out of the valid range."""
        response = client_with_auth.post(
            "/api/v1/documents/operational",
            data={
                "collection_name": "ops",
                "ezshare_id": "EZ-102",
                "year": "3000",  # year > 2100 is invalid
            },
            files={"file": ("doc.pdf", b"pdf content", "application/pdf")},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Publication endpoint — POST /api/v1/documents/publication
# ---------------------------------------------------------------------------


class TestPublicationUploadEndpoint:
    """Tests for POST /api/v1/documents/publication."""

    def test_upload_with_minimal_fields(
        self, client_with_auth: TestClient, mock_use_case: MagicMock
    ) -> None:
        """201 is returned with just the required fields."""
        container = Container()
        with container.upload_and_enqueue_document_use_case.override(mock_use_case):
            response = client_with_auth.post(
                "/api/v1/documents/publication",
                data={
                    "collection_name": "pubs",
                    "ezshare_id": "EZ-200",
                },
                files={"file": ("paper.pdf", b"pdf content", "application/pdf")},
            )
        assert response.status_code == 201

    def test_upload_with_all_publication_fields(
        self, client_with_auth: TestClient, mock_use_case: MagicMock
    ) -> None:
        """201 is returned with full publication metadata."""
        container = Container()
        with container.upload_and_enqueue_document_use_case.override(mock_use_case):
            response = client_with_auth.post(
                "/api/v1/documents/publication",
                data={
                    "collection_name": "pubs",
                    "ezshare_id": "EZ-201",
                    "journal": "Journal of Development Economics",
                    "doi": "10.1234/jde.2024.001",
                    "issn": "0304-3878",
                    "peer_reviewed": "true",
                    "publication_type": "journal_article",
                    "country": "Brazil",
                    "year": "2024",
                    "language": "en",
                    "document_name": "Development Paper",
                    "tags": "economics,development",
                },
                files={"file": ("paper.pdf", b"pdf content", "application/pdf")},
            )
        assert response.status_code == 201
        call_args = mock_use_case.execute.call_args[0][0]
        assert call_args.metadata.get("document_category") == "publication"
        assert call_args.metadata.get("journal") == "Journal of Development Economics"
        assert call_args.metadata.get("doi") == "10.1234/jde.2024.001"

    def test_rejects_missing_required_fields(self, client_with_auth: TestClient) -> None:
        """422 is returned when collection_name or ezshare_id is missing."""
        response = client_with_auth.post(
            "/api/v1/documents/publication",
            data={"journal": "Nature"},
            files={"file": ("paper.pdf", b"pdf content", "application/pdf")},
        )
        assert response.status_code == 422

    def test_rejects_invalid_year_value(
        self, client_with_auth: TestClient
    ) -> None:
        """422 is returned when year is out of the valid range."""
        response = client_with_auth.post(
            "/api/v1/documents/publication",
            data={
                "collection_name": "pubs",
                "ezshare_id": "EZ-202",
                "year": "1800",  # year < 1900 is invalid
            },
            files={"file": ("paper.pdf", b"pdf content", "application/pdf")},
        )
        assert response.status_code == 422
