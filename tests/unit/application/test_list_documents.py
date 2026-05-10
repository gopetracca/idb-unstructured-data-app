"""Unit tests for ListDocumentsUseCase."""

import base64
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.application.dto.document_dto import ListDocumentsInput
from src.application.use_cases.list_documents import ListDocumentsUseCase
from src.core.entities.composites import DocumentComplete
from src.core.entities.document import Document
from src.core.entities.pipeline_state import PipelineState
from src.core.value_objects.document_metadata import DocumentMetadata, OperationalDocumentMetadata


def create_document_complete(
    file_id: str,
    filename: str,
    document_type: str | None = None,
    tags: list[str] | None = None,
    source: str | None = None,
    department: str | None = None,
    created_offset_days: int = 0,
    operation_number: str | None = None,
    country: str | None = None,
    sector: str | None = None,
    year: int | None = None,
    disclosed: bool | None = None,
) -> DocumentComplete:
    """Helper to create DocumentComplete with metadata and promoted fields."""
    return DocumentComplete(
        document=Document(
            tenant_id="tenant-123",
            file_id=file_id,
            blob_name=filename,
            content_type="application/pdf",
            size_bytes=1000,
            upload_timestamp=datetime.utcnow() - timedelta(days=created_offset_days),
            last_updated=datetime.utcnow() - timedelta(days=created_offset_days),
            collection_name="test-collection",
        ),
        pipeline=PipelineState(file_id=file_id),
        metadata=OperationalDocumentMetadata(
            file_id=file_id,
            document_type=document_type,
            operation_number=operation_number,
            country=country,
            sector=sector,
            year=year,
            disclosed=disclosed,
            tags=tags or [],
            source=source,
            department=department,
        ),
    )


@pytest.fixture
def sample_documents() -> list[DocumentComplete]:
    """Create sample documents for testing."""
    return [
        create_document_complete("file-1", "report1.pdf", "report", ["ai", "ml"], "research", "R&D", 0),
        create_document_complete("file-2", "manual1.pdf", "manual", ["docs"], "support", "Support", 1),
        create_document_complete("file-3", "report2.pdf", "report", ["ai", "nlp"], "research", "R&D", 2),
        create_document_complete("file-4", "spec1.pdf", "specification", ["api"], "engineering", "Engineering", 3),
        create_document_complete("file-5", "guide1.pdf", "guide", ["ml"], "training", "HR", 4),
    ]


@pytest.fixture
def mock_metadata_store(sample_documents: list[DocumentComplete]) -> AsyncMock:
    """Create mock metadata store."""
    mock = AsyncMock()
    mock.query_with_filters = AsyncMock(return_value=sample_documents)
    mock.count_by_tenant = AsyncMock(return_value=len(sample_documents))
    return mock


@pytest.fixture
def use_case(mock_metadata_store: AsyncMock) -> ListDocumentsUseCase:
    """Create use case with mocks."""
    return ListDocumentsUseCase(metadata_store=mock_metadata_store)


class TestListDocumentsUseCase:
    """Tests for ListDocumentsUseCase."""

    async def test_list_all_documents(
        self,
        use_case: ListDocumentsUseCase,
        sample_documents: list[DocumentComplete],
    ) -> None:
        """Test listing all documents without filters."""
        input_dto = ListDocumentsInput(
            tenant_id="tenant-123",
            limit=20,
        )

        result = await use_case.execute(input_dto)

        assert len(result.documents) == 5
        assert result.pagination.total_count == 5
        assert result.pagination.has_next is False
        assert result.pagination.has_previous is False

    async def test_filter_by_document_type_passes_to_repository(
        self,
        use_case: ListDocumentsUseCase,
        mock_metadata_store: AsyncMock,
    ) -> None:
        """Test that document_type filter is passed as promoted filter to repository."""
        input_dto = ListDocumentsInput(
            tenant_id="tenant-123",
            document_type="report",
        )

        await use_case.execute(input_dto)

        # document_type is now a promoted field filter (server-side SQL)
        call_args = mock_metadata_store.query_with_filters.call_args
        filters = call_args.kwargs["filters"]
        assert filters.document_type == "report"

    async def test_filter_by_tags(
        self,
        use_case: ListDocumentsUseCase,
    ) -> None:
        """Test filtering by tags."""
        input_dto = ListDocumentsInput(
            tenant_id="tenant-123",
            tags=["ml"],
        )

        result = await use_case.execute(input_dto)

        assert len(result.documents) == 2  # file-1 and file-5 have "ml" tag
        for doc in result.documents:
            assert "ml" in doc.metadata.tags

    async def test_filter_by_source(
        self,
        use_case: ListDocumentsUseCase,
    ) -> None:
        """Test filtering by source."""
        input_dto = ListDocumentsInput(
            tenant_id="tenant-123",
            source="research",
        )

        result = await use_case.execute(input_dto)

        assert len(result.documents) == 2
        for doc in result.documents:
            assert doc.metadata.source == "research"

    async def test_filter_by_department(
        self,
        use_case: ListDocumentsUseCase,
    ) -> None:
        """Test filtering by department."""
        input_dto = ListDocumentsInput(
            tenant_id="tenant-123",
            department="R&D",
        )

        result = await use_case.execute(input_dto)

        assert len(result.documents) == 2
        for doc in result.documents:
            assert doc.metadata.department == "R&D"

    async def test_sort_by_created_at_desc(
        self,
        use_case: ListDocumentsUseCase,
    ) -> None:
        """Test sorting by created_at descending (default)."""
        input_dto = ListDocumentsInput(
            tenant_id="tenant-123",
            sort_by="created_at",
            sort_order="desc",
        )

        result = await use_case.execute(input_dto)

        # First document should be most recent (file-1)
        assert result.documents[0].file_id == "file-1"
        # Last should be oldest (file-5)
        assert result.documents[-1].file_id == "file-5"

    async def test_sort_by_created_at_asc(
        self,
        use_case: ListDocumentsUseCase,
    ) -> None:
        """Test sorting by created_at ascending."""
        input_dto = ListDocumentsInput(
            tenant_id="tenant-123",
            sort_by="created_at",
            sort_order="asc",
        )

        result = await use_case.execute(input_dto)

        # First document should be oldest (file-5)
        assert result.documents[0].file_id == "file-5"
        # Last should be most recent (file-1)
        assert result.documents[-1].file_id == "file-1"

    async def test_sort_by_filename(
        self,
        use_case: ListDocumentsUseCase,
    ) -> None:
        """Test sorting by filename."""
        input_dto = ListDocumentsInput(
            tenant_id="tenant-123",
            sort_by="filename",
            sort_order="asc",
        )

        result = await use_case.execute(input_dto)

        filenames = [doc.filename for doc in result.documents]
        assert filenames == sorted(filenames)

    async def test_pagination_limit(
        self,
        use_case: ListDocumentsUseCase,
    ) -> None:
        """Test pagination with limit."""
        input_dto = ListDocumentsInput(
            tenant_id="tenant-123",
            limit=2,
        )

        result = await use_case.execute(input_dto)

        assert len(result.documents) == 2
        assert result.pagination.total_count == 5
        assert result.pagination.has_next is True
        assert result.pagination.next_cursor is not None

    async def test_pagination_cursor(
        self,
        use_case: ListDocumentsUseCase,
    ) -> None:
        """Test pagination with cursor."""
        # First page
        input_dto = ListDocumentsInput(
            tenant_id="tenant-123",
            limit=2,
        )
        first_page = await use_case.execute(input_dto)

        # Second page
        input_dto = ListDocumentsInput(
            tenant_id="tenant-123",
            limit=2,
            cursor=first_page.pagination.next_cursor,
        )
        second_page = await use_case.execute(input_dto)

        # Documents should be different
        first_ids = {doc.file_id for doc in first_page.documents}
        second_ids = {doc.file_id for doc in second_page.documents}
        assert first_ids.isdisjoint(second_ids)

        # Second page should have has_previous
        assert second_page.pagination.has_previous is True

    async def test_empty_result(
        self,
        use_case: ListDocumentsUseCase,
        mock_metadata_store: AsyncMock,
    ) -> None:
        """Test empty result when no documents match."""
        mock_metadata_store.query_with_filters.return_value = []

        input_dto = ListDocumentsInput(
            tenant_id="tenant-empty",
        )

        result = await use_case.execute(input_dto)

        assert len(result.documents) == 0
        assert result.pagination.total_count == 0
        assert result.pagination.has_next is False
        assert result.pagination.has_previous is False

    async def test_promoted_fields_merged_into_metadata_response(
        self,
        use_case: ListDocumentsUseCase,
        mock_metadata_store: AsyncMock,
    ) -> None:
        """Test that promoted fields from DocumentComplete are merged into metadata DTO."""
        docs = [create_document_complete(
            "file-1", "doc1.pdf",
            document_type="operational",
            country="Uruguay",
            year=2024,
        )]
        mock_metadata_store.query_with_filters.return_value = docs

        input_dto = ListDocumentsInput(tenant_id="tenant-123")
        result = await use_case.execute(input_dto)

        assert len(result.documents) == 1
        doc = result.documents[0]
        # Promoted fields should be merged into metadata
        doc_meta = doc.metadata.model_dump()
        assert doc_meta.get("document_type") == "operational"
        assert doc_meta.get("country") == "Uruguay"
        assert doc_meta.get("year") == 2024


class TestPromotedFieldFiltering:
    """Tests for promoted field filtering functionality."""

    @pytest.fixture
    def documents_with_promoted_fields(self) -> list[DocumentComplete]:
        """Create sample documents with promoted fields."""
        return [
            create_document_complete(
                "file-1", "doc1.pdf", "report", operation_number="UR-P1180",
                country="Uruguay", sector="TRANSPORT", year=2023, disclosed=True,
            ),
            create_document_complete(
                "file-2", "doc2.pdf", "manual", operation_number="BR-P2345",
                country="Brazil", sector="ENERGY", year=2022, disclosed=False,
            ),
            create_document_complete(
                "file-3", "doc3.pdf", "report", operation_number="UR-P1180",
                country="Uruguay", sector="TRANSPORT", year=2024, disclosed=True,
            ),
            create_document_complete(
                "file-4", "doc4.pdf", "specification", operation_number="AR-P5678",
                country="Argentina", sector="HEALTH", year=2023, disclosed=True,
            ),
        ]

    @pytest.fixture
    def mock_store_with_promoted(
        self,
        documents_with_promoted_fields: list[DocumentComplete],
    ) -> AsyncMock:
        """Create mock store that returns promoted field documents."""
        mock = AsyncMock()
        mock.query_with_filters = AsyncMock(return_value=documents_with_promoted_fields)
        return mock

    @pytest.fixture
    def use_case_promoted(self, mock_store_with_promoted: AsyncMock) -> ListDocumentsUseCase:
        """Create use case with promoted field mock."""
        return ListDocumentsUseCase(metadata_store=mock_store_with_promoted)

    async def test_filter_by_operation_number(
        self,
        use_case_promoted: ListDocumentsUseCase,
        mock_store_with_promoted: AsyncMock,
    ) -> None:
        """Test filtering by operation_number passes to repository."""
        input_dto = ListDocumentsInput(
            tenant_id="tenant-123",
            operation_number="UR-P1180",
        )

        await use_case_promoted.execute(input_dto)

        mock_store_with_promoted.query_with_filters.assert_called_once()
        call_args = mock_store_with_promoted.query_with_filters.call_args
        filters = call_args.kwargs["filters"]
        assert filters.operation_number == "UR-P1180"

    async def test_filter_by_country_and_sector(
        self,
        use_case_promoted: ListDocumentsUseCase,
        mock_store_with_promoted: AsyncMock,
    ) -> None:
        """Test filtering by multiple promoted fields."""
        input_dto = ListDocumentsInput(
            tenant_id="tenant-123",
            country="Uruguay",
            sector="TRANSPORT",
        )

        await use_case_promoted.execute(input_dto)

        call_args = mock_store_with_promoted.query_with_filters.call_args
        filters = call_args.kwargs["filters"]
        assert filters.country == "Uruguay"
        assert filters.sector == "TRANSPORT"

    async def test_filter_by_disclosed_boolean(
        self,
        use_case_promoted: ListDocumentsUseCase,
        mock_store_with_promoted: AsyncMock,
    ) -> None:
        """Test filtering by disclosed boolean field."""
        input_dto = ListDocumentsInput(
            tenant_id="tenant-123",
            disclosed=True,
        )

        await use_case_promoted.execute(input_dto)

        call_args = mock_store_with_promoted.query_with_filters.call_args
        filters = call_args.kwargs["filters"]
        assert filters.disclosed is True

    async def test_filter_by_year(
        self,
        use_case_promoted: ListDocumentsUseCase,
        mock_store_with_promoted: AsyncMock,
    ) -> None:
        """Test filtering by exact year."""
        input_dto = ListDocumentsInput(
            tenant_id="tenant-123",
            year=2023,
        )

        await use_case_promoted.execute(input_dto)

        call_args = mock_store_with_promoted.query_with_filters.call_args
        filters = call_args.kwargs["filters"]
        assert filters.year == 2023

    async def test_combined_promoted_and_json_filters(
        self,
        use_case_promoted: ListDocumentsUseCase,
        mock_store_with_promoted: AsyncMock,
        documents_with_promoted_fields: list[DocumentComplete],
    ) -> None:
        """Test combining promoted field and JSON metadata filters."""
        mock_store_with_promoted.query_with_filters.return_value = [
            documents_with_promoted_fields[0],  # file-1: UR-P1180, report
            documents_with_promoted_fields[2],  # file-3: UR-P1180, report
        ]

        input_dto = ListDocumentsInput(
            tenant_id="tenant-123",
            country="Uruguay",  # Promoted field
            sector="TRANSPORT",  # Promoted field
            document_type="report",  # Promoted field (now server-side)
        )

        await use_case_promoted.execute(input_dto)

        # Verify promoted filters passed to repository
        call_args = mock_store_with_promoted.query_with_filters.call_args
        filters = call_args.kwargs["filters"]
        assert filters.country == "Uruguay"
        assert filters.sector == "TRANSPORT"
        assert filters.document_type == "report"

    async def test_sort_by_operation_number(
        self,
        use_case_promoted: ListDocumentsUseCase,
        documents_with_promoted_fields: list[DocumentComplete],
    ) -> None:
        """Test sorting by operation_number."""
        input_dto = ListDocumentsInput(
            tenant_id="tenant-123",
            sort_by="operation_number",
            sort_order="asc",
        )

        result = await use_case_promoted.execute(input_dto)

        # Should be sorted: AR-P5678, BR-P2345, UR-P1180, UR-P1180
        assert result.documents[0].file_id == "file-4"  # AR-P5678
        assert result.documents[1].file_id == "file-2"  # BR-P2345

    async def test_sort_by_year(
        self,
        use_case_promoted: ListDocumentsUseCase,
        documents_with_promoted_fields: list[DocumentComplete],
    ) -> None:
        """Test sorting by year."""
        input_dto = ListDocumentsInput(
            tenant_id="tenant-123",
            sort_by="year",
            sort_order="desc",
        )

        result = await use_case_promoted.execute(input_dto)

        # Should be sorted: 2024, 2023, 2023, 2022
        assert result.documents[0].file_id == "file-3"  # 2024
        assert result.documents[-1].file_id == "file-2"  # 2022


class TestPaginationCursor:
    """Tests for cursor-based pagination."""

    async def test_cursor_encoding(
        self,
        use_case: ListDocumentsUseCase,
    ) -> None:
        """Test that cursors are properly encoded."""
        input_dto = ListDocumentsInput(
            tenant_id="tenant-123",
            limit=2,
        )

        result = await use_case.execute(input_dto)

        # Decode cursor
        cursor_data = json.loads(
            base64.b64decode(result.pagination.next_cursor).decode("utf-8")
        )

        assert "index" in cursor_data
        assert cursor_data["index"] == 2  # After first 2 items

    async def test_invalid_cursor_starts_from_beginning(
        self,
        use_case: ListDocumentsUseCase,
    ) -> None:
        """Test that invalid cursor falls back to start."""
        input_dto = ListDocumentsInput(
            tenant_id="tenant-123",
            limit=2,
            cursor="invalid-cursor",
        )

        result = await use_case.execute(input_dto)

        assert len(result.documents) == 2
        assert result.pagination.has_previous is False
