"""Unit tests for IngestDocumentsUseCase."""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from src.application.dto.ingestion_dto import (
    IngestDocumentsInput,
    IngestionDocument,
)
from src.application.use_cases.ingest_documents import IngestDocumentsUseCase
from src.core.entities.composites import DocumentComplete
from src.core.entities.document import Document
from src.core.entities.pipeline_state import OverallStatus, PipelineState, ProcessingStage
from src.core.value_objects.document_metadata import OperationalDocumentMetadata
from src.core.errors import (
    IndexNotFoundError,
    VectorDimensionMismatchError,
)


@pytest.fixture
def mock_vector_database():
    """Create a mock vector database port."""
    return AsyncMock()


@pytest.fixture
def mock_document_store():
    """Create a mock document store."""
    return AsyncMock()


@pytest.fixture
def use_case(mock_vector_database, mock_document_store):
    """Create IngestDocumentsUseCase with mocked dependencies."""
    return IngestDocumentsUseCase(
        vector_database=mock_vector_database,
        document_store=mock_document_store,
    )


@pytest.fixture
def sample_documents():
    """Create sample ingestion documents."""
    return [
        IngestionDocument(
            id="file1_chunk0",
            chunk_id="chunk0",
            file_id="file1",
            text="Sample text content 1",
            vector=[0.1, 0.2, 0.3],
            metadata={"model_version": "test", "token_count": 10},
        ),
        IngestionDocument(
            id="file1_chunk1",
            chunk_id="chunk1",
            file_id="file1",
            text="Sample text content 2",
            vector=[0.4, 0.5, 0.6],
            metadata={"model_version": "test", "token_count": 12},
        ),
    ]


class TestIngestDocuments:
    """Tests for execute method."""

    async def test_ingest_documents_success(
        self, use_case, mock_vector_database, mock_document_store, sample_documents
    ):
        """Test successful document ingestion."""
        # Arrange
        input_dto = IngestDocumentsInput(
            tenant_id="test-tenant",
            collection_name="test-collection",
            documents=sample_documents,
            correlation_id="test-correlation-id",
        )

        # Mock collection info
        mock_vector_database.get_index.return_value = {
            "name": "test-collection",
            "vector_dimension": 3,
            "embedding_model": "test",
        }

        # Mock document store (no document found)
        mock_document_store.get_by_id.return_value = None

        # Mock successful upsert
        mock_vector_database.upsert_documents.return_value = [
            "file1_chunk0",
            "file1_chunk1",
        ]

        # Act
        result = await use_case.execute(input_dto)

        # Assert
        assert result.collection_name == "test-collection"
        assert result.total_documents == 2
        assert result.successful == 2
        assert result.failed == 0
        assert result.failed_ids == []
        assert result.processing_time_ms >= 0  # May be 0 for very fast operations
        assert result.correlation_id == "test-correlation-id"

        mock_vector_database.get_index.assert_called_once_with("test-collection")
        mock_vector_database.upsert_documents.assert_called_once()

    async def test_ingest_documents_dimension_mismatch(
        self, use_case, mock_vector_database, sample_documents
    ):
        """Test ingestion with vector dimension mismatch."""
        # Arrange
        input_dto = IngestDocumentsInput(
            tenant_id="test-tenant",
            collection_name="test-collection",
            documents=sample_documents,
            correlation_id="test-correlation-id",
        )

        # Mock collection with different dimension
        mock_vector_database.get_index.return_value = {
            "name": "test-collection",
            "vector_dimension": 1536,  # Different from document vectors (3)
        }

        # Act & Assert
        with pytest.raises(VectorDimensionMismatchError) as exc_info:
            await use_case.execute(input_dto)

        assert "dimension mismatch" in str(exc_info.value).lower()

    async def test_ingest_documents_collection_not_found(
        self, use_case, mock_vector_database, sample_documents
    ):
        """Test ingestion to non-existent collection."""
        # Arrange
        input_dto = IngestDocumentsInput(
            tenant_id="test-tenant",
            collection_name="non-existent",
            documents=sample_documents,
            correlation_id="test-correlation-id",
        )

        mock_vector_database.get_index.side_effect = IndexNotFoundError("non-existent")

        # Act & Assert
        with pytest.raises(IndexNotFoundError):
            await use_case.execute(input_dto)

    async def test_ingest_documents_partial_failure(
        self, use_case, mock_vector_database, mock_document_store, sample_documents
    ):
        """Test ingestion with partial failures."""
        # Arrange
        input_dto = IngestDocumentsInput(
            tenant_id="test-tenant",
            collection_name="test-collection",
            documents=sample_documents,
            correlation_id="test-correlation-id",
        )

        # Mock collection info
        mock_vector_database.get_index.return_value = {
            "name": "test-collection",
            "vector_dimension": 3,
            "embedding_model": "test",
        }

        # No document found in store (no metadata enrichment)
        mock_document_store.get_by_id.return_value = None

        # Mock partial success (only first document succeeded)
        mock_vector_database.upsert_documents.return_value = ["file1_chunk0"]

        # Act
        result = await use_case.execute(input_dto)

        # Assert
        assert result.collection_name == "test-collection"
        assert result.total_documents == 2
        assert result.successful == 1
        assert result.failed == 1
        assert "file1_chunk1" in result.failed_ids
        assert result.processing_time_ms >= 0  # May be 0 for very fast operations
        assert result.correlation_id == "test-correlation-id"

    async def test_ingest_single_document(
        self, use_case, mock_vector_database, mock_document_store
    ):
        """Test ingestion of a single document."""
        # Arrange
        single_doc = IngestionDocument(
            id="file1_chunk0",
            chunk_id="chunk0",
            file_id="file1",
            text="Single document",
            vector=[0.1, 0.2],
            metadata={},
        )

        input_dto = IngestDocumentsInput(
            tenant_id="test-tenant",
            collection_name="test-collection",
            documents=[single_doc],
            correlation_id="test-correlation-id",
        )

        # Mock collection info
        mock_vector_database.get_index.return_value = {
            "name": "test-collection",
            "vector_dimension": 2,
        }

        mock_document_store.get_by_id.return_value = None

        # Mock successful upsert
        mock_vector_database.upsert_documents.return_value = ["file1_chunk0"]

        # Act
        result = await use_case.execute(input_dto)

        # Assert
        assert result.total_documents == 1
        assert result.successful == 1
        assert result.failed == 0

    async def test_ingest_documents_with_metadata(
        self, use_case, mock_vector_database, mock_document_store
    ):
        """Test ingestion of documents with complex metadata."""
        # Arrange
        doc_with_metadata = IngestionDocument(
            id="file1_chunk0",
            chunk_id="chunk0",
            file_id="file1",
            text="Document with metadata",
            vector=[0.1, 0.2, 0.3],
            metadata={
                "model_version": "text-embedding-3-small",
                "token_count": 128,
                "chunking_strategy": "sentence",
                "chunk_size": 512,
                "overlap_chars": 50,
            },
        )

        input_dto = IngestDocumentsInput(
            tenant_id="test-tenant",
            collection_name="test-collection",
            documents=[doc_with_metadata],
            correlation_id="test-correlation-id",
        )

        # Mock collection info
        mock_vector_database.get_index.return_value = {
            "name": "test-collection",
            "vector_dimension": 3,
            "embedding_model": "text-embedding-3-small",
        }

        mock_document_store.get_by_id.return_value = None

        # Mock successful upsert
        mock_vector_database.upsert_documents.return_value = ["file1_chunk0"]

        # Act
        result = await use_case.execute(input_dto)

        # Assert
        assert result.successful == 1

        # Verify chunk-level metadata was passed through to SearchableMetadata
        call_args = mock_vector_database.upsert_documents.call_args
        ingested_doc = call_args[0][1][0]  # First doc in the list
        assert ingested_doc.metadata.model_version == "text-embedding-3-small"
        assert ingested_doc.metadata.token_count == 128

    async def test_ingest_documents_mixed_dimensions(
        self, use_case, mock_vector_database, mock_document_store
    ):
        """Test ingestion fails when documents have different vector dimensions."""
        # Arrange
        mock_document_store.get_by_id.return_value = None
        mixed_docs = [
            IngestionDocument(
                id="file1_chunk0",
                chunk_id="chunk0",
                file_id="file1",
                text="Document 1",
                vector=[0.1, 0.2, 0.3],
                metadata={},
            ),
            IngestionDocument(
                id="file1_chunk1",
                chunk_id="chunk1",
                file_id="file1",
                text="Document 2",
                vector=[0.1, 0.2],  # Different dimension
                metadata={},
            ),
        ]

        input_dto = IngestDocumentsInput(
            tenant_id="test-tenant",
            collection_name="test-collection",
            documents=mixed_docs,
            correlation_id="test-correlation-id",
        )

        # Mock collection info
        mock_vector_database.get_index.return_value = {
            "name": "test-collection",
            "vector_dimension": 3,
            "embedding_model": "test",
        }

        # Act & Assert
        with pytest.raises(VectorDimensionMismatchError):
            await use_case.execute(input_dto)


class TestMetadataEnrichment:
    """Tests for metadata enrichment with DocumentComplete."""

    async def test_enrich_metadata_with_document_complete(
        self, use_case, mock_vector_database, mock_document_store
    ):
        """Test that metadata is enriched with DocumentComplete fields."""
        # Arrange
        sample_doc = IngestionDocument(
            id="file1_chunk0",
            chunk_id="chunk0",
            file_id="file1",
            text="Sample text",
            vector=[0.1, 0.2, 0.3],
            metadata={"model_version": "test", "token_count": 10},
        )

        input_dto = IngestDocumentsInput(
            tenant_id="test-tenant",
            collection_name="test-collection",
            documents=[sample_doc],
            correlation_id="test-correlation-id",
        )

        # Mock collection info
        mock_vector_database.get_index.return_value = {
            "name": "test-collection",
            "vector_dimension": 3,
            "embedding_model": "test",
        }

        # Mock DocumentComplete with promoted fields
        doc_complete = DocumentComplete(
            document=Document(
                tenant_id="test-tenant",
                file_id="file1",
                blob_name="test.pdf",
                ezshare_id="EZSHARE-123",
            ),
            pipeline=PipelineState(
                file_id="file1",
                current_stage=ProcessingStage.INGEST,
                overall_status=OverallStatus.PROCESSING,
            ),
            metadata=OperationalDocumentMetadata(
                file_id="file1",
                operation_number="UR-P1180",
                document_name="Test Project Document",
                document_author="John Doe",
                sector="TRANSPORT",
                country="Uruguay",
                operation_type="LOAN",
                dept_id="EXR/CMG",
                disclosed=True,
                year=2024,
                file_extension=".pdf",
                document_publish_date=datetime(2024, 1, 15),
            ),
        )

        mock_document_store.get_by_id.return_value = doc_complete
        mock_vector_database.upsert_documents.return_value = ["file1_chunk0"]

        # Act
        result = await use_case.execute(input_dto)

        # Assert
        assert result.successful == 1

        # Verify enriched metadata was passed to vector database
        call_args = mock_vector_database.upsert_documents.call_args
        ingested_doc = call_args[0][1][0]

        # Check chunk-level metadata is preserved
        assert ingested_doc.metadata.model_version == "test"
        assert ingested_doc.metadata.token_count == 10

        # Check promoted fields are added
        assert ingested_doc.metadata.operation_number == "UR-P1180"
        assert ingested_doc.metadata.document_name == "Test Project Document"
        assert ingested_doc.metadata.document_author == "John Doe"
        assert ingested_doc.metadata.sector == "TRANSPORT"
        assert ingested_doc.metadata.country == "Uruguay"
        assert ingested_doc.metadata.operation_type == "LOAN"
        assert ingested_doc.metadata.dept_id == "EXR/CMG"
        assert ingested_doc.metadata.disclosed is True
        assert ingested_doc.metadata.year == 2024
        assert ingested_doc.metadata.file_extension == ".pdf"
        assert ingested_doc.metadata.document_publish_date == "2024-01-15T00:00:00Z"

        # Check ezshare_id from document entity
        assert ingested_doc.metadata.ezshare_id == "EZSHARE-123"

    async def test_enrich_metadata_without_document_complete(
        self, use_case, mock_vector_database, mock_document_store
    ):
        """Test ingestion works gracefully when DocumentComplete is not found."""
        # Arrange
        sample_doc = IngestionDocument(
            id="file1_chunk0",
            chunk_id="chunk0",
            file_id="file1",
            text="Sample text",
            vector=[0.1, 0.2, 0.3],
            metadata={"model_version": "test", "token_count": 10},
        )

        input_dto = IngestDocumentsInput(
            tenant_id="test-tenant",
            collection_name="test-collection",
            documents=[sample_doc],
            correlation_id="test-correlation-id",
        )

        # Mock collection info
        mock_vector_database.get_index.return_value = {
            "name": "test-collection",
            "vector_dimension": 3,
            "embedding_model": "test",
        }

        # Mock document store not found
        mock_document_store.get_by_id.return_value = None
        mock_vector_database.upsert_documents.return_value = ["file1_chunk0"]

        # Act
        result = await use_case.execute(input_dto)

        # Assert
        assert result.successful == 1

        # Verify only chunk metadata is present (no enrichment)
        call_args = mock_vector_database.upsert_documents.call_args
        ingested_doc = call_args[0][1][0]

        assert ingested_doc.metadata.model_version == "test"
        assert ingested_doc.metadata.token_count == 10
        assert ingested_doc.metadata.operation_number is None
        assert ingested_doc.metadata.sector is None

    async def test_enrich_metadata_batch_fetch(
        self, use_case, mock_vector_database, mock_document_store
    ):
        """Test efficient batch fetching of DocumentComplete for multiple files."""
        # Arrange
        docs = [
            IngestionDocument(
                id="file1_chunk0",
                chunk_id="chunk0",
                file_id="file1",
                text="Text 1",
                vector=[0.1, 0.2, 0.3],
                metadata={"token_count": 10},
            ),
            IngestionDocument(
                id="file1_chunk1",
                chunk_id="chunk1",
                file_id="file1",
                text="Text 2",
                vector=[0.4, 0.5, 0.6],
                metadata={"token_count": 12},
            ),
            IngestionDocument(
                id="file2_chunk0",
                chunk_id="chunk0",
                file_id="file2",
                text="Text 3",
                vector=[0.7, 0.8, 0.9],
                metadata={"token_count": 15},
            ),
        ]

        input_dto = IngestDocumentsInput(
            tenant_id="test-tenant",
            collection_name="test-collection",
            documents=docs,
            correlation_id="test-correlation-id",
        )

        # Mock collection info
        mock_vector_database.get_index.return_value = {
            "name": "test-collection",
            "vector_dimension": 3,
            "embedding_model": "test",
        }

        # Mock DocumentComplete for both files
        doc_complete_1 = DocumentComplete(
            document=Document(
                tenant_id="test-tenant",
                file_id="file1",
                blob_name="test1.pdf",
            ),
            pipeline=PipelineState(
                file_id="file1",
                current_stage=ProcessingStage.INGEST,
                overall_status=OverallStatus.PROCESSING,
            ),
            metadata=OperationalDocumentMetadata(
                file_id="file1",
                sector="TRANSPORT",
            ),
        )

        doc_complete_2 = DocumentComplete(
            document=Document(
                tenant_id="test-tenant",
                file_id="file2",
                blob_name="test2.pdf",
            ),
            pipeline=PipelineState(
                file_id="file2",
                current_stage=ProcessingStage.INGEST,
                overall_status=OverallStatus.PROCESSING,
            ),
            metadata=OperationalDocumentMetadata(
                file_id="file2",
                sector="ENERGY",
            ),
        )

        async def get_by_id_side_effect(tenant_id, file_id):
            if file_id == "file1":
                return doc_complete_1
            elif file_id == "file2":
                return doc_complete_2
            return None

        mock_document_store.get_by_id.side_effect = get_by_id_side_effect
        mock_vector_database.upsert_documents.return_value = [
            "file1_chunk0",
            "file1_chunk1",
            "file2_chunk0",
        ]

        # Act
        result = await use_case.execute(input_dto)

        # Assert
        assert result.successful == 3

        # Verify DocumentComplete was fetched for each unique file_id
        assert mock_document_store.get_by_id.call_count == 2

        # Verify enrichment
        call_args = mock_vector_database.upsert_documents.call_args
        ingested_docs = call_args[0][1]

        # First two chunks should have TRANSPORT sector
        assert ingested_docs[0].metadata.sector == "TRANSPORT"
        assert ingested_docs[1].metadata.sector == "TRANSPORT"

        # Third chunk should have ENERGY sector
        assert ingested_docs[2].metadata.sector == "ENERGY"

    async def test_enrich_metadata_handles_repository_error(
        self, use_case, mock_vector_database, mock_document_store
    ):
        """Test graceful handling of document store errors."""
        # Arrange
        sample_doc = IngestionDocument(
            id="file1_chunk0",
            chunk_id="chunk0",
            file_id="file1",
            text="Sample text",
            vector=[0.1, 0.2, 0.3],
            metadata={"model_version": "test"},
        )

        input_dto = IngestDocumentsInput(
            tenant_id="test-tenant",
            collection_name="test-collection",
            documents=[sample_doc],
            correlation_id="test-correlation-id",
        )

        # Mock collection info
        mock_vector_database.get_index.return_value = {
            "name": "test-collection",
            "vector_dimension": 3,
            "embedding_model": "test",
        }

        # Mock document store error
        mock_document_store.get_by_id.side_effect = Exception(
            "Database connection error"
        )
        mock_vector_database.upsert_documents.return_value = ["file1_chunk0"]

        # Act - should not raise exception
        result = await use_case.execute(input_dto)

        # Assert - ingestion should succeed without enrichment
        assert result.successful == 1

    async def test_enrich_metadata_datetime_formatting(
        self, use_case, mock_vector_database, mock_document_store
    ):
        """Test that datetime fields are formatted as UTC DateTimeOffset strings."""
        # Arrange
        sample_doc = IngestionDocument(
            id="file1_chunk0",
            chunk_id="chunk0",
            file_id="file1",
            text="Sample text",
            vector=[0.1, 0.2, 0.3],
            metadata={},
        )

        input_dto = IngestDocumentsInput(
            tenant_id="test-tenant",
            collection_name="test-collection",
            documents=[sample_doc],
            correlation_id="test-correlation-id",
        )

        # Mock collection info
        mock_vector_database.get_index.return_value = {
            "name": "test-collection",
            "vector_dimension": 3,
            "embedding_model": "test",
        }

        # Mock DocumentComplete with datetime fields
        doc_complete = DocumentComplete(
            document=Document(
                tenant_id="test-tenant",
                file_id="file1",
                blob_name="test.pdf",
            ),
            pipeline=PipelineState(
                file_id="file1",
                current_stage=ProcessingStage.INGEST,
                overall_status=OverallStatus.PROCESSING,
            ),
            metadata=OperationalDocumentMetadata(
                file_id="file1",
                document_publish_date=datetime(2024, 3, 15, 10, 30, 0),
                document_approval_date=datetime(2024, 3, 10, 14, 0, 0),
                document_created_date=datetime(2024, 3, 1, 9, 0, 0),
            ),
        )

        mock_document_store.get_by_id.return_value = doc_complete
        mock_vector_database.upsert_documents.return_value = ["file1_chunk0"]

        # Act
        result = await use_case.execute(input_dto)

        # Assert
        call_args = mock_vector_database.upsert_documents.call_args
        ingested_doc = call_args[0][1][0]

        # Verify document_publish_date is serialized as ISO string in SearchableMetadata
        assert isinstance(ingested_doc.metadata.document_publish_date, str)
        assert ingested_doc.metadata.document_publish_date == "2024-03-15T10:30:00Z"

