"""Unit tests for SQLAlchemy ORM models - entity mapping roundtrips."""

import json
from datetime import datetime

import pytest
import sqlalchemy as sa

from src.core.entities.chunk_index import ChunkIndex
from src.core.entities.chunk_metadata_index import ChunkMetadataIndex, EmbeddingStatus
from src.core.entities.document import Document
from src.core.entities.pipeline_state import OverallStatus, PipelineState, ProcessingStage
from src.core.value_objects.document_metadata import DocumentMetadata, OperationalDocumentMetadata
from src.infrastructure.sqlserver.models.chunk_metadata_model import ChunkMetadataTable
from src.infrastructure.sqlserver.models.chunk_model import ChunkTable
from src.infrastructure.sqlserver.models.chunk_vector_ref_model import ChunkVectorRefTable
from src.infrastructure.sqlserver.models.file_metadata_model import FileMetadataTable
from src.infrastructure.sqlserver.models.file_model import FileTable
from src.infrastructure.sqlserver.models.pipeline_state_model import PipelineStateTable
from src.infrastructure.sqlserver.models.processing_event_model import ProcessingEventTable


@pytest.mark.unit
class TestFileTableModel:
    """Tests for FileTable <-> Document mapping."""

    def _sample_document(self) -> Document:
        return Document(
            tenant_id="test-tenant",
            file_id="file-001",
            blob_name="report.pdf",
            content_type="application/pdf",
            size_bytes=1024,
            content_hash="abc123",
            file_version=1,
            collection_name="my-collection",
            ezshare_id="EZSHARE-123",
        )

    def _sample_pipeline_state(self) -> PipelineState:
        return PipelineState(
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
        )

    def _sample_metadata(self) -> OperationalDocumentMetadata:
        return OperationalDocumentMetadata(
            file_id="file-001",
            document_type="operational",
            language="en",
            operation_number=None,
            document_name="Annual Report",
            document_author="John Doe",
            country="US",
            sector="TRANSPORT",
            year=2024,
            file_extension=".pdf",
            disclosed=True,
        )

    def test_from_entity_creates_file_table(self):
        entity = self._sample_document()
        row = FileTable.from_entity(entity)

        assert row.file_id == "file-001"
        assert row.tenant_id == "test-tenant"
        assert row.blob_name == "report.pdf"
        assert row.content_type == "application/pdf"
        assert row.size_bytes == 1024
        assert row.collection_name == "my-collection"
        assert row.ezshare_id == "EZSHARE-123"

    def test_update_from_entity(self):
        entity = self._sample_document()
        row = FileTable.from_entity(entity)

        entity.file_version = 2
        entity.content_hash = "new_hash"
        row.update_from_entity(entity)

        assert row.file_version == 2
        assert row.content_hash == "new_hash"

    def test_from_entity_metadata_record(self):
        metadata = self._sample_metadata()
        row = FileMetadataTable.from_entity(metadata)

        assert row.file_id == "file-001"
        assert row.document_type == "operational"
        assert row.language == "en"
        assert row.country == "US"
        assert row.sector == "TRANSPORT"
        assert row.year == 2024
        assert row.document_name == "Annual Report"
        assert row.document_author == "John Doe"
        assert row.file_extension == ".pdf"
        assert row.disclosed is True
        assert row.operation_number is None

    def test_metadata_update_from_entity(self):
        metadata = self._sample_metadata()
        row = FileMetadataTable.from_entity(metadata)

        metadata.country = "BR"
        metadata.year = 2025
        metadata.document_type = "report"
        row.update_from_entity(metadata)

        assert row.country == "BR"
        assert row.year == 2025
        assert row.document_type == "report"

    def test_metadata_record_has_no_metadata_json(self):
        """Verify file_metadata table no longer has metadata_json column."""
        metadata = self._sample_metadata()
        row = FileMetadataTable.from_entity(metadata)

        assert not hasattr(row, "metadata_json") or "metadata_json" not in FileMetadataTable.__table__.columns

    def test_pipeline_state_from_entity(self):
        pipeline = self._sample_pipeline_state()
        row = PipelineStateTable.from_entity(pipeline)

        assert row.file_id == "file-001"
        assert row.current_stage == "chunk"
        assert row.overall_status == "processing"
        assert row.chunk_count == 10
        assert row.embedded_chunk_count == 5
        assert isinstance(row.last_updated, datetime)

    def test_pipeline_state_update_from_entity(self):
        pipeline = self._sample_pipeline_state()
        row = PipelineStateTable.from_entity(pipeline)

        pipeline.mark_processing(ProcessingStage.VECTORIZE)
        pipeline.chunk_count = 20
        row.update_from_entity(pipeline)

        assert row.current_stage == "vectorize"
        assert row.chunk_count == 20

    def test_pipeline_chunking_strategy_column_is_text(self):
        chunking_column = PipelineStateTable.__table__.columns["chunking_strategy"]
        assert isinstance(chunking_column.type, sa.Text)


@pytest.mark.unit
class TestChunkTableModel:
    """Tests for ChunkTable <-> ChunkIndex mapping."""

    def _sample_chunk_index(self) -> ChunkIndex:
        return ChunkIndex(
            file_id="file-001",
            chunk_id="chunk-001",
            chunk_index=0,
            text_preview="This is a sample text preview...",
            start_char=0,
            end_char=100,
            page_number=1,
        )

    def test_from_entity_creates_chunk_table(self):
        entity = self._sample_chunk_index()
        row = ChunkTable.from_entity(entity)

        assert row.chunk_id == "chunk-001"
        assert row.file_id == "file-001"
        assert row.chunk_index == 0
        assert row.text_preview == "This is a sample text preview..."
        assert row.start_char == 0
        assert row.end_char == 100
        assert row.page_number == 1

    def test_to_entity_roundtrip(self):
        entity = self._sample_chunk_index()
        row = ChunkTable.from_entity(entity)
        restored = row.to_entity()

        assert restored.chunk_id == entity.chunk_id
        assert restored.file_id == entity.file_id
        assert restored.chunk_index == entity.chunk_index
        assert restored.start_char == entity.start_char
        assert restored.end_char == entity.end_char
        assert restored.page_number == entity.page_number

    def test_update_from_entity(self):
        entity = self._sample_chunk_index()
        row = ChunkTable.from_entity(entity)

        entity.text_preview = "Updated preview"
        row.update_from_entity(entity)

        assert row.text_preview == "Updated preview"

    def test_text_preview_truncation(self):
        entity = self._sample_chunk_index()
        entity.text_preview = "x" * 600
        row = ChunkTable.from_entity(entity)

        assert len(row.text_preview) == 500

    def test_null_page_number(self):
        entity = self._sample_chunk_index()
        entity.page_number = None
        row = ChunkTable.from_entity(entity)
        restored = row.to_entity()

        assert restored.page_number is None


@pytest.mark.unit
class TestChunkMetadataTableModel:
    """Tests for ChunkMetadataTable <-> ChunkMetadataIndex mapping."""

    def _sample_chunk_metadata(self) -> ChunkMetadataIndex:
        return ChunkMetadataIndex(
            chunk_id="chunk-001",
            embedding_status=EmbeddingStatus.PENDING,
            metadata_json={"token_count": 128},
        )

    def test_from_entity_creates_chunk_metadata_table(self):
        entity = self._sample_chunk_metadata()
        row = ChunkMetadataTable.from_entity(entity)

        assert row.chunk_id == "chunk-001"
        assert row.embedding_status == EmbeddingStatus.PENDING.value
        assert row.metadata_json == {"token_count": 128}

    def test_to_entity_roundtrip(self):
        entity = self._sample_chunk_metadata()
        row = ChunkMetadataTable.from_entity(entity)
        restored = row.to_entity()

        assert restored.chunk_id == entity.chunk_id
        assert restored.embedding_status == entity.embedding_status
        assert restored.metadata_json == entity.metadata_json

    def test_update_from_entity(self):
        entity = self._sample_chunk_metadata()
        row = ChunkMetadataTable.from_entity(entity)

        entity.embedding_status = EmbeddingStatus.COMPLETED
        entity.metadata_json = {"token_count": 256}
        row.update_from_entity(entity)

        assert row.embedding_status == EmbeddingStatus.COMPLETED.value
        assert row.metadata_json == {"token_count": 256}


@pytest.mark.unit
class TestChunkVectorRefModel:
    """Tests for ChunkVectorRefTable creation."""

    def test_create_vector_ref(self):
        ref = ChunkVectorRefTable(
            chunk_id="chunk-001",
            db_name="azure-ai-search",
            vector_doc_id="vec-abc-123",
        )

        assert ref.chunk_id == "chunk-001"
        assert ref.db_name == "azure-ai-search"
        assert ref.vector_doc_id == "vec-abc-123"

    def test_vector_ref_table_name(self):
        assert ChunkVectorRefTable.__tablename__ == "chunk_vector_refs"


@pytest.mark.unit
class TestProcessingEventTableModel:
    """Tests for ProcessingEventTable creation and fields."""

    def test_create_processing_event_row(self):
        now = datetime.utcnow()
        row = ProcessingEventTable(
            file_id="file-001",
            tenant_id="test-tenant",
            stage="convert",
            status="success",
            event_timestamp=now,
            duration_ms=1500,
            error_message=None,
            metadata_json=None,
        )

        assert row.file_id == "file-001"
        assert row.tenant_id == "test-tenant"
        assert row.stage == "convert"
        assert row.status == "success"
        assert row.event_timestamp == now
        assert row.duration_ms == 1500
        assert row.error_message is None
        assert row.metadata_json is None

    def test_create_failed_event_with_error(self):
        row = ProcessingEventTable(
            file_id="file-002",
            tenant_id="test-tenant",
            stage="chunk",
            status="failed",
            event_timestamp=datetime.utcnow(),
            error_message="Chunking failed: out of memory",
            metadata_json='{"retry_attempt": 2}',
        )

        assert row.status == "failed"
        assert row.error_message == "Chunking failed: out of memory"
        assert json.loads(row.metadata_json) == {"retry_attempt": 2}

    def test_initial_stage_has_null_from_stage(self):
        row = ProcessingEventTable(
            file_id="file-001",
            tenant_id="test-tenant",
            stage="dispatcher",
            status="success",
            event_timestamp=datetime.utcnow(),
        )

        assert row.stage == "dispatcher"

    def test_table_name(self):
        assert ProcessingEventTable.__tablename__ == "processing_events"


@pytest.mark.unit
class TestFileTableToEntityRoundtrip:
    """Tests for FileTable full roundtrip to Document entity."""

    def test_to_entity_produces_document(self):
        """Test FileTable.to_entity produces correct Document."""
        now = datetime.utcnow()
        file_row = FileTable(
            file_id="file-rt-001",
            tenant_id="tenant-rt",
            blob_name="doc.pdf",
            content_type="application/pdf",
            size_bytes=2048,
            content_hash="hash123",
            file_version=2,
            upload_timestamp=now,
            last_updated=now,
            collection_name="coll-1",
            ezshare_id="EZ-100",
        )

        entity = file_row.to_entity()

        assert entity.file_id == "file-rt-001"
        assert entity.tenant_id == "tenant-rt"
        assert entity.blob_name == "doc.pdf"
        assert entity.size_bytes == 2048
        assert entity.file_version == 2
        assert entity.collection_name == "coll-1"
        assert entity.ezshare_id == "EZ-100"

    def test_metadata_to_entity_roundtrip(self):
        """Test FileMetadataTable.to_entity produces correct DocumentMetadata."""
        metadata_row = FileMetadataTable(
            file_id="file-rt-001",
            document_type="operational",
            language="pt",
            country="BR",
            sector="ENERGY",
            year=2025,
            document_name="Energy Report",
            document_author="Jane",
            file_extension=".docx",
            disclosed=False,
            operation_number="UR-P1180",
        )

        entity = metadata_row.to_entity()

        assert entity.file_id == "file-rt-001"
        assert entity.document_type == "operational"
        assert entity.language == "pt"
        assert entity.country == "BR"
        assert entity.sector == "ENERGY"
        assert entity.year == 2025
        assert entity.document_name == "Energy Report"
        assert entity.file_extension == ".docx"
        assert entity.disclosed is False
        assert entity.operation_number == "UR-P1180"

    def test_pipeline_state_to_entity_roundtrip(self):
        """Test PipelineStateTable.to_entity produces correct PipelineState."""
        now = datetime.utcnow()
        pipeline_row = PipelineStateTable(
            file_id="file-rt-001",
            current_stage="vectorize",
            overall_status="processing",
            chunk_count=15,
            embedded_chunk_count=10,
            chunking_strategy="semantic",
            embedding_model="text-embedding-3-large",
            vector_db_targets='["azure-ai-search"]',
            error_message="",
            retry_count=1,
            last_updated=now,
        )

        entity = pipeline_row.to_entity()

        assert entity.file_id == "file-rt-001"
        assert entity.current_stage == ProcessingStage.VECTORIZE
        assert entity.overall_status == OverallStatus.PROCESSING
        assert entity.chunk_count == 15
        assert entity.embedded_chunk_count == 10

    def test_to_entity_without_metadata(self):
        """Test FileTable.to_entity works without metadata record."""
        now = datetime.utcnow()
        file_row = FileTable(
            file_id="file-no-meta",
            tenant_id="tenant-1",
            blob_name="doc.pdf",
            content_type="application/pdf",
            size_bytes=100,
            content_hash="hash",
            file_version=1,
            upload_timestamp=now,
            last_updated=now,
        )

        entity = file_row.to_entity()

        assert entity.file_id == "file-no-meta"
        assert entity.blob_name == "doc.pdf"
