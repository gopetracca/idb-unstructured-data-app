"""Unit tests for SQL Server repositories with mocked async sessions."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.entities.chunk_index import ChunkIndex
from src.core.entities.composites import DocumentComplete
from src.core.entities.document import Document
from src.core.entities.pipeline_state import OverallStatus, PipelineState, ProcessingStage
from src.core.entities.processing_event import ProcessingEvent, StageDurationStats
from src.core.value_objects.document_metadata import OperationalDocumentMetadata
from src.infrastructure.sqlserver.models.chunk_model import ChunkTable
from src.infrastructure.sqlserver.models.file_metadata_model import FileMetadataTable
from src.infrastructure.sqlserver.models.file_model import FileTable
from src.infrastructure.sqlserver.repositories.chunk_index_repository import (
    ChunkIndexRepositorySQLServer,
)
from src.infrastructure.sqlserver.repositories.document_repository import (
    DocumentRepositorySQLServer,
)
from src.infrastructure.sqlserver.repositories.processing_events_repository import (
    ProcessingEventsRepositorySQLServer,
)


def _sample_document_complete() -> DocumentComplete:
    """Create a sample DocumentComplete composite for testing."""
    return DocumentComplete(
        document=Document(
            tenant_id="test-tenant",
            file_id="file-001",
            blob_name="report.pdf",
            content_type="application/pdf",
            size_bytes=1024,
            content_hash="abc123",
            file_version=1,
            collection_name="my-collection",
            ezshare_id="EZSHARE-123",
        ),
        pipeline=PipelineState(
            file_id="file-001",
            current_stage=ProcessingStage.CHUNK,
            overall_status=OverallStatus.PROCESSING,
            chunk_count=10,
            embedded_chunk_count=5,
            chunking_strategy="fixed_size",
            embedding_model="text-embedding-3-small",
            vector_db_targets='["azure-ai-search"]',
            error_message="",
            retry_count=0,
        ),
        metadata=OperationalDocumentMetadata(
            file_id="file-001",
            document_name="Annual Report",
            document_author="John Doe",
            country="US",
            sector="TRANSPORT",
            year=2024,
            file_extension=".pdf",
            disclosed=True,
        ),
    )


def _sample_chunk_index() -> ChunkIndex:
    """Create a sample ChunkIndex entity for testing."""
    return ChunkIndex(
        file_id="file-001",
        chunk_id="chunk-001",
        chunk_index=0,
        text_preview="This is a sample text preview...",
        start_char=0,
        end_char=100,
        page_number=1,
    )


def _make_chunk_table_row(chunk_index: ChunkIndex) -> MagicMock:
    """Create a mock ChunkTable row with to_entity and update_from_entity."""
    row = MagicMock(spec=ChunkTable)
    row.to_entity.return_value = chunk_index
    row.update_from_entity = MagicMock()
    return row


class MockSessionContext:
    """Helper to create a properly mocked async session factory context.

    Usage:
        ctx = MockSessionContext()
        repo = DocumentRepositorySQLServer(session_factory=ctx.factory)
        # Configure ctx.session.execute to return what you need
    """

    def __init__(self):
        self.session = AsyncMock()
        self.session.add = MagicMock()
        self.session.add_all = MagicMock()
        self.session.commit = AsyncMock()
        self.session.rollback = AsyncMock()
        self.session.refresh = AsyncMock()
        self.session.execute = AsyncMock()

        # Build a context manager that returns self.session
        self.factory = MagicMock()
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=self.session)
        cm.__aexit__ = AsyncMock(return_value=False)
        self.factory.return_value = cm

    def set_scalar_one_or_none(self, value):
        """Configure execute to return a result whose unique().scalar_one_or_none() returns value."""
        mock_result = MagicMock()
        unique_result = MagicMock()
        unique_result.scalar_one_or_none.return_value = value
        mock_result.unique.return_value = unique_result
        self.session.execute.return_value = mock_result

    def set_scalars_all(self, values):
        """Configure execute to return result.unique().scalars().all() as values."""
        mock_result = MagicMock()
        unique_result = MagicMock()
        scalars_obj = MagicMock()
        scalars_obj.all.return_value = values
        unique_result.scalars.return_value = scalars_obj
        mock_result.unique.return_value = unique_result
        self.session.execute.return_value = mock_result

    def set_scalar_one(self, value):
        """Configure execute to return result.scalar_one() as value."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = value
        self.session.execute.return_value = mock_result

    def set_rowcount(self, count):
        """Configure execute to return result.rowcount as count."""
        mock_result = MagicMock()
        mock_result.rowcount = count
        self.session.execute.return_value = mock_result


# =============================================================================
# DocumentRepositorySQLServer Tests
# =============================================================================


@pytest.mark.unit
class TestDocumentRepositorySQLServer:
    """Tests for DocumentRepositorySQLServer."""

    def _make_repo(self, ctx: MockSessionContext) -> DocumentRepositorySQLServer:
        return DocumentRepositorySQLServer(session_factory=ctx.factory)

    async def test_get_by_id_not_found(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)
        ctx.set_scalar_one_or_none(None)

        result = await repo.get_by_id("test-tenant", "nonexistent")

        assert result is None

    async def test_delete_returns_true(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)
        ctx.set_rowcount(1)

        result = await repo.delete("test-tenant", "file-001")

        assert result is True
        ctx.session.commit.assert_called_once()

    async def test_delete_returns_false_when_not_found(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)
        ctx.set_rowcount(0)

        result = await repo.delete("test-tenant", "nonexistent")

        assert result is False

    async def test_count_by_tenant(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)
        ctx.set_scalar_one(42)

        result = await repo.count_by_tenant("test-tenant")

        assert result == 42

    async def test_count_by_status(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)
        ctx.set_scalar_one(7)

        result = await repo.count_by_status("test-tenant", OverallStatus.PROCESSING)

        assert result == 7

    async def test_close_is_noop(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)

        await repo.close()  # Should not raise


# =============================================================================
# ChunkIndexRepositorySQLServer Tests
# =============================================================================


@pytest.mark.unit
class TestChunkIndexRepositorySQLServer:
    """Tests for ChunkIndexRepositorySQLServer."""

    def _make_repo(self, ctx: MockSessionContext) -> ChunkIndexRepositorySQLServer:
        return ChunkIndexRepositorySQLServer(session_factory=ctx.factory)

    async def test_create(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)
        entity = _sample_chunk_index()

        result = await repo.create(entity)

        assert result == entity
        ctx.session.add.assert_called_once()
        ctx.session.commit.assert_called_once()

    async def test_get_by_id_found(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)
        entity = _sample_chunk_index()
        row = _make_chunk_table_row(entity)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = row
        ctx.session.execute.return_value = mock_result

        result = await repo.get_by_id("chunk-001")

        assert result == entity

    async def test_get_by_id_not_found(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        ctx.session.execute.return_value = mock_result

        result = await repo.get_by_id("nonexistent")

        assert result is None

    async def test_update_existing(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)
        entity = _sample_chunk_index()
        row = _make_chunk_table_row(entity)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = row
        ctx.session.execute.return_value = mock_result

        result = await repo.update(entity)

        assert result == entity
        row.update_from_entity.assert_called_once_with(entity)
        ctx.session.commit.assert_called_once()

    async def test_update_not_found_raises(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)
        entity = _sample_chunk_index()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        ctx.session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="ChunkIndex not found"):
            await repo.update(entity)

    async def test_batch_create(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)
        chunks = [_sample_chunk_index() for _ in range(3)]

        result = await repo.batch_create(chunks)

        assert len(result) == 3
        assert ctx.session.add.call_count == 3
        ctx.session.commit.assert_called_once()

    async def test_batch_create_empty(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)

        result = await repo.batch_create([])

        assert result == []
        ctx.session.add.assert_not_called()

    async def test_delete(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)
        ctx.set_rowcount(1)

        result = await repo.delete("chunk-001")

        assert result is True
        ctx.session.commit.assert_called_once()

    async def test_delete_not_found(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)
        ctx.set_rowcount(0)

        result = await repo.delete("nonexistent")

        assert result is False

    async def test_query_by_file(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)
        entity = _sample_chunk_index()
        row = _make_chunk_table_row(entity)

        mock_result = MagicMock()
        scalars_obj = MagicMock()
        scalars_obj.all.return_value = [row]
        mock_result.scalars.return_value = scalars_obj
        ctx.session.execute.return_value = mock_result

        result = await repo.query_by_file("file-001")

        assert len(result) == 1
        assert result[0] == entity

    async def test_query_by_file_page(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)
        entity = _sample_chunk_index()
        row = _make_chunk_table_row(entity)

        mock_result = MagicMock()
        scalars_obj = MagicMock()
        scalars_obj.all.return_value = [row]
        mock_result.scalars.return_value = scalars_obj
        ctx.session.execute.return_value = mock_result

        result = await repo.query_by_file_page("file-001", offset=2, limit=3)

        assert len(result) == 1
        assert result[0] == entity

    async def test_count_by_file(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)
        ctx.set_scalar_one(10)

        result = await repo.count_by_file("file-001")

        assert result == 10

    async def test_count_embedded(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)
        ctx.set_scalar_one(5)

        result = await repo.count_embedded("file-001")

        assert result == 5

    async def test_delete_by_file(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)
        ctx.set_rowcount(8)

        result = await repo.delete_by_file("file-001")

        assert result == 8
        ctx.session.commit.assert_called_once()

    async def test_mark_embedded(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)
        entity = _sample_chunk_index()
        row = _make_chunk_table_row(entity)

        chunk_result = MagicMock()
        chunk_result.scalar_one_or_none.return_value = row
        meta_result = MagicMock()
        meta_result.scalar_one_or_none.return_value = None
        ctx.session.execute = AsyncMock(side_effect=[chunk_result, meta_result])

        result = await repo.mark_embedded(
            "chunk-001", "vec-123", "azure-ai-search"
        )

        assert result is not None
        assert ctx.session.add.call_count == 2  # metadata row + vector ref
        ctx.session.commit.assert_called_once()

    async def test_mark_embedded_not_found(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        ctx.session.execute.return_value = mock_result

        result = await repo.mark_embedded(
            "nonexistent", "vec-123"
        )

        assert result is None

    async def test_mark_failed(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)
        entity = _sample_chunk_index()
        row = _make_chunk_table_row(entity)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = row
        meta_result = MagicMock()
        meta_result.scalar_one_or_none.return_value = MagicMock()
        ctx.session.execute = AsyncMock(side_effect=[mock_result, meta_result])

        result = await repo.mark_failed("chunk-001")

        assert result is not None
        ctx.session.commit.assert_called_once()

    async def test_get_chunk_ids_for_db(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)

        mock_result = MagicMock()
        mock_result.all.return_value = [("vec-001",), ("vec-002",)]
        ctx.session.execute.return_value = mock_result

        result = await repo.get_chunk_ids_for_db("file-001")

        assert result == ["vec-001", "vec-002"]

    async def test_close_is_noop(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)

        await repo.close()  # Should not raise


# =============================================================================
# ProcessingEventsRepositorySQLServer Tests
# =============================================================================


@pytest.mark.unit
class TestProcessingEventsRepositorySQLServer:
    """Tests for ProcessingEventsRepositorySQLServer."""

    def _make_repo(self, ctx: MockSessionContext) -> ProcessingEventsRepositorySQLServer:
        return ProcessingEventsRepositorySQLServer(session_factory=ctx.factory)

    async def test_log_stage_event_success(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)

        # After commit + refresh, mock the row to have an event_id
        async def mock_refresh(row):
            row.event_id = 1

        ctx.session.refresh = AsyncMock(side_effect=mock_refresh)

        result = await repo.log_stage_event(
            file_id="file-001",
            tenant_id="test-tenant",
            stage="convert",
            status="success",
            duration_ms=1500,
        )

        assert result.file_id == "file-001"
        assert result.stage == "convert"
        assert result.status == "success"
        assert result.duration_ms == 1500
        ctx.session.add.assert_called_once()
        ctx.session.commit.assert_called_once()

    async def test_log_stage_event_first_event_no_duration(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)

        # No previous event — _calculate_duration returns None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        ctx.session.execute.return_value = mock_result

        async def mock_refresh(row):
            row.event_id = 1

        ctx.session.refresh = AsyncMock(side_effect=mock_refresh)

        result = await repo.log_stage_event(
            file_id="file-001",
            tenant_id="test-tenant",
            stage="dispatcher",
            status="success",
        )

        assert result.stage == "dispatcher"
        assert result.duration_ms is None

    async def test_log_stage_event_with_error(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)

        async def mock_refresh(row):
            row.event_id = 2

        ctx.session.refresh = AsyncMock(side_effect=mock_refresh)

        result = await repo.log_stage_event(
            file_id="file-001",
            tenant_id="test-tenant",
            stage="chunk",
            status="failed",
            duration_ms=500,
            error_message="Chunking error",
        )

        assert result.status == "failed"
        assert result.error_message == "Chunking error"
        assert result.duration_ms == 500

    async def test_log_stage_event_auto_calculates_duration(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)

        # Mock previous timestamp lookup
        prev_time = datetime.utcnow() - timedelta(seconds=2)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = prev_time
        ctx.session.execute.return_value = mock_result

        async def mock_refresh(row):
            row.event_id = 3

        ctx.session.refresh = AsyncMock(side_effect=mock_refresh)

        result = await repo.log_stage_event(
            file_id="file-001",
            tenant_id="test-tenant",
            stage="chunk",
            status="success",
            # duration_ms not provided - should auto-calculate
        )

        assert result.duration_ms is not None
        assert result.duration_ms >= 2000  # At least 2 seconds

    async def test_get_file_timeline(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)

        now = datetime.utcnow()
        entity1 = ProcessingEvent(
            event_id=1,
            file_id="file-001",
            tenant_id="test-tenant",
            stage="dispatcher",
            status="success",
            event_timestamp=now - timedelta(seconds=10),
            duration_ms=None,
            error_message=None,
            metadata_json=None,
        )
        entity2 = ProcessingEvent(
            event_id=2,
            file_id="file-001",
            tenant_id="test-tenant",
            stage="convert",
            status="success",
            event_timestamp=now,
            duration_ms=10000,
            error_message=None,
            metadata_json=None,
        )
        row1 = MagicMock()
        row1.to_entity.return_value = entity1
        row2 = MagicMock()
        row2.to_entity.return_value = entity2

        mock_result = MagicMock()
        scalars_obj = MagicMock()
        scalars_obj.all.return_value = [row1, row2]
        mock_result.scalars.return_value = scalars_obj
        ctx.session.execute.return_value = mock_result

        result = await repo.get_file_timeline("file-001", tenant_id="test-tenant")

        assert len(result) == 2
        assert result[0].stage == "dispatcher"
        assert result[1].stage == "convert"
        assert isinstance(result[0], ProcessingEvent)

    async def test_get_file_timeline_empty(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)

        mock_result = MagicMock()
        scalars_obj = MagicMock()
        scalars_obj.all.return_value = []
        mock_result.scalars.return_value = scalars_obj
        ctx.session.execute.return_value = mock_result

        result = await repo.get_file_timeline("nonexistent", tenant_id="test-tenant")

        assert result == []

    async def test_get_stage_statistics(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)

        stats_rows = [
            MagicMock(
                stage="convert",
                avg_duration_ms=2500.5,
                min_duration_ms=1000,
                max_duration_ms=5000,
                sample_count=10,
            ),
            MagicMock(
                stage="chunk",
                avg_duration_ms=1200.0,
                min_duration_ms=500,
                max_duration_ms=3000,
                sample_count=8,
            ),
        ]

        mock_result = MagicMock()
        mock_result.all.return_value = stats_rows
        ctx.session.execute.return_value = mock_result

        result = await repo.get_stage_statistics("test-tenant")

        assert len(result) == 2
        assert isinstance(result[0], StageDurationStats)
        assert result[0].stage == "convert"
        assert result[0].avg_duration_ms == 2500.5
        assert result[0].sample_count == 10
        assert result[1].stage == "chunk"

    async def test_get_failed_transitions(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)

        now = datetime.utcnow()
        entity = ProcessingEvent(
            event_id=5,
            file_id="file-002",
            tenant_id="test-tenant",
            stage="chunk",
            status="failed",
            event_timestamp=now,
            duration_ms=None,
            error_message="Out of memory",
            metadata_json=None,
        )
        row = MagicMock()
        row.to_entity.return_value = entity

        mock_result = MagicMock()
        scalars_obj = MagicMock()
        scalars_obj.all.return_value = [row]
        mock_result.scalars.return_value = scalars_obj
        ctx.session.execute.return_value = mock_result

        result = await repo.get_failed_transitions("test-tenant", limit=10)

        assert len(result) == 1
        assert result[0].status == "failed"
        assert result[0].error_message == "Out of memory"
        assert isinstance(result[0], ProcessingEvent)

    async def test_get_failed_transitions_empty(self):
        ctx = MockSessionContext()
        repo = self._make_repo(ctx)

        mock_result = MagicMock()
        scalars_obj = MagicMock()
        scalars_obj.all.return_value = []
        mock_result.scalars.return_value = scalars_obj
        ctx.session.execute.return_value = mock_result

        result = await repo.get_failed_transitions("test-tenant")

        assert result == []
