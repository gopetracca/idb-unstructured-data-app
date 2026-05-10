"""Unit tests for ProcessDocumentUseCase."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.dto.document_analysis import (
    DocumentAnalysisRequest,
    ProcessingStatus,
)
from src.application.use_cases.process_document import ProcessDocumentUseCase
from src.core.entities.composites import DocumentWithPipeline
from src.core.entities.document import Document
from src.core.entities.document_analysis import (
    ExtractionMetadata,
    MarkdownOutput,
    PageContent,
)
from src.core.entities.pipeline_state import OverallStatus, PipelineState, ProcessingStage
from src.core.errors import (
    DocumentNotFoundError,
    DocumentProcessingError,
    UnsupportedFormatError,
)


@pytest.fixture
def mock_pipeline_store(sample_document_with_pipeline: DocumentWithPipeline) -> MagicMock:
    """Create a mock PipelineStorePort."""
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=sample_document_with_pipeline)
    repo.mark_processing = AsyncMock(return_value=sample_document_with_pipeline.pipeline)
    repo.mark_failed = AsyncMock(return_value=sample_document_with_pipeline.pipeline)
    repo.update_blob_references = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def process_document_use_case(
    mock_blob_client: MagicMock,
    mock_document_intelligence_adapter: MagicMock,
    mock_pipeline_store: MagicMock,
    sample_markdown_output: MarkdownOutput,
) -> ProcessDocumentUseCase:
    """Create a ProcessDocumentUseCase with mock dependencies."""
    # Set up the mock adapter to return the sample output
    mock_document_intelligence_adapter.analyze_document = AsyncMock(
        return_value=sample_markdown_output
    )

    return ProcessDocumentUseCase(
        blob_client=mock_blob_client,
        document_intelligence=mock_document_intelligence_adapter,
        pipeline_store=mock_pipeline_store,
    )


class TestProcessDocumentUseCase:
    """Tests for ProcessDocumentUseCase."""

    async def test_execute_success(
        self,
        process_document_use_case: ProcessDocumentUseCase,
        sample_file_id: str,
        sample_tenant_id: str,
    ):
        """Test successful document processing."""
        request = DocumentAnalysisRequest(
            file_id=sample_file_id,
            tenant_id=sample_tenant_id,
            source_container="raw",
            output_container="text",
        )

        result = await process_document_use_case.execute(request)

        assert result.file_id == sample_file_id
        assert result.status == ProcessingStatus.COMPLETED
        assert result.markdown_url is not None
        assert "text" in result.markdown_url
        assert result.correlation_id is not None
        assert result.processing_time_ms is not None
        assert result.processing_time_ms >= 0

    async def test_execute_downloads_document(
        self,
        process_document_use_case: ProcessDocumentUseCase,
        mock_blob_client: MagicMock,
        sample_file_id: str,
        sample_tenant_id: str,
    ):
        """Test that execute downloads the document from blob storage."""
        request = DocumentAnalysisRequest(
            file_id=sample_file_id,
            tenant_id=sample_tenant_id,
        )

        await process_document_use_case.execute(request)

        mock_blob_client.download_blob.assert_called_once()
        call_args = mock_blob_client.download_blob.call_args
        assert call_args[0][0] == "raw"  # container
        assert sample_file_id in call_args[0][1]  # blob path contains file_id
        assert sample_tenant_id in call_args[0][1]  # blob path contains tenant_id

    async def test_execute_uses_correct_blob_path_format(
        self,
        process_document_use_case: ProcessDocumentUseCase,
        mock_blob_client: MagicMock,
        sample_document_with_pipeline: DocumentWithPipeline,
        sample_file_id: str,
        sample_tenant_id: str,
    ):
        """Test that blob path is read from document.raw_blob_ref (SSOT)."""
        request = DocumentAnalysisRequest(
            file_id=sample_file_id,
            tenant_id=sample_tenant_id,
        )

        await process_document_use_case.execute(request)

        # Verify blob_exists was called with raw_blob_ref from Document (SSOT)
        exists_call = mock_blob_client.blob_exists.call_args
        blob_path = exists_call[0][1]
        expected_path = sample_document_with_pipeline.document.raw_blob_ref
        assert blob_path == expected_path, f"Expected path '{expected_path}', got '{blob_path}'"

        # Verify download_blob was called with same path
        download_call = mock_blob_client.download_blob.call_args
        assert download_call[0][1] == expected_path

    async def test_execute_uploads_markdown(
        self,
        process_document_use_case: ProcessDocumentUseCase,
        mock_blob_client: MagicMock,
        sample_file_id: str,
        sample_tenant_id: str,
    ):
        """Test that execute uploads markdown to text container with correct path."""
        request = DocumentAnalysisRequest(
            file_id=sample_file_id,
            tenant_id=sample_tenant_id,
        )

        await process_document_use_case.execute(request)

        mock_blob_client.upload_blob.assert_called_once()
        call_args = mock_blob_client.upload_blob.call_args
        assert call_args[1]["container"] == "text"
        assert call_args[1]["content_type"] == "application/json; charset=utf-8"
        # Verify output path includes tenant_id: tenant_id/file_id/text.json
        expected_output_path = f"{sample_tenant_id}/{sample_file_id}/text.json"
        assert call_args[1]["blob_path"] == expected_output_path

    async def test_execute_document_not_found_in_index(
        self,
        mock_blob_client: MagicMock,
        mock_document_intelligence_adapter: MagicMock,
        sample_file_id: str,
        sample_tenant_id: str,
    ):
        """Test handling when file_id is not in pipeline store."""
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        use_case = ProcessDocumentUseCase(
            blob_client=mock_blob_client,
            document_intelligence=mock_document_intelligence_adapter,
            pipeline_store=mock_repo,
        )

        request = DocumentAnalysisRequest(
            file_id=sample_file_id,
            tenant_id=sample_tenant_id,
        )

        with pytest.raises(DocumentNotFoundError) as exc_info:
            await use_case.execute(request)

        assert sample_file_id in str(exc_info.value.message)

    async def test_execute_blob_not_found(
        self,
        mock_blob_client: MagicMock,
        mock_document_intelligence_adapter: MagicMock,
        mock_pipeline_store: MagicMock,
        sample_file_id: str,
        sample_tenant_id: str,
    ):
        """Test handling when blob doesn't exist."""
        mock_blob_client.blob_exists = AsyncMock(return_value=False)

        use_case = ProcessDocumentUseCase(
            blob_client=mock_blob_client,
            document_intelligence=mock_document_intelligence_adapter,
            pipeline_store=mock_pipeline_store,
        )

        request = DocumentAnalysisRequest(
            file_id=sample_file_id,
            tenant_id=sample_tenant_id,
        )

        with pytest.raises(DocumentNotFoundError):
            await use_case.execute(request)

    async def test_execute_unsupported_format(
        self,
        mock_blob_client: MagicMock,
        mock_pipeline_store: MagicMock,
        sample_document_with_pipeline: DocumentWithPipeline,
        sample_file_id: str,
        sample_tenant_id: str,
    ):
        """Test handling of unsupported document formats."""
        # Set up a file with unsupported content type
        sample_document_with_pipeline.document.content_type = "application/unknown"
        mock_pipeline_store.get_by_id = AsyncMock(return_value=sample_document_with_pipeline)

        mock_adapter = MagicMock()
        mock_adapter.is_format_supported = MagicMock(return_value=False)
        mock_adapter.get_supported_formats = MagicMock(
            return_value=["application/pdf", "image/png"]
        )

        use_case = ProcessDocumentUseCase(
            blob_client=mock_blob_client,
            document_intelligence=mock_adapter,
            pipeline_store=mock_pipeline_store,
        )

        request = DocumentAnalysisRequest(
            file_id=sample_file_id,
            tenant_id=sample_tenant_id,
        )

        with pytest.raises(UnsupportedFormatError) as exc_info:
            await use_case.execute(request)

        assert "application/unknown" in exc_info.value.content_type

    async def test_execute_processing_error(
        self,
        mock_blob_client: MagicMock,
        mock_pipeline_store: MagicMock,
        sample_file_id: str,
        sample_tenant_id: str,
    ):
        """Test handling of processing errors."""
        mock_adapter = MagicMock()
        mock_adapter.is_format_supported = MagicMock(return_value=True)
        mock_adapter.analyze_document = AsyncMock(
            side_effect=Exception("Processing failed")
        )

        use_case = ProcessDocumentUseCase(
            blob_client=mock_blob_client,
            document_intelligence=mock_adapter,
            pipeline_store=mock_pipeline_store,
        )

        request = DocumentAnalysisRequest(
            file_id=sample_file_id,
            tenant_id=sample_tenant_id,
        )

        with pytest.raises(DocumentProcessingError) as exc_info:
            await use_case.execute(request)

        assert sample_file_id == exc_info.value.file_id
        mock_pipeline_store.mark_failed.assert_called_once()

    async def test_execute_marks_processing_stage(
        self,
        process_document_use_case: ProcessDocumentUseCase,
        mock_pipeline_store: MagicMock,
        sample_file_id: str,
        sample_tenant_id: str,
    ):
        """Test that execute updates processing stage."""
        request = DocumentAnalysisRequest(
            file_id=sample_file_id,
            tenant_id=sample_tenant_id,
        )

        await process_document_use_case.execute(request)

        mock_pipeline_store.mark_processing.assert_called_once()
        call_args = mock_pipeline_store.mark_processing.call_args
        assert call_args[0][2] == ProcessingStage.CONVERT

    async def test_execute_with_custom_containers(
        self,
        process_document_use_case: ProcessDocumentUseCase,
        mock_blob_client: MagicMock,
        sample_file_id: str,
        sample_tenant_id: str,
    ):
        """Test using custom source and output containers."""
        request = DocumentAnalysisRequest(
            file_id=sample_file_id,
            tenant_id=sample_tenant_id,
            source_container="custom-raw",
            output_container="custom-text",
        )

        await process_document_use_case.execute(request)

        # Check source container
        exists_call = mock_blob_client.blob_exists.call_args
        assert exists_call[0][0] == "custom-raw"

        # Check output container
        upload_call = mock_blob_client.upload_blob.call_args
        assert upload_call[1]["container"] == "custom-text"

    async def test_execute_with_correlation_id(
        self,
        process_document_use_case: ProcessDocumentUseCase,
        sample_file_id: str,
        sample_tenant_id: str,
    ):
        """Test that provided correlation_id is used."""
        correlation_id = "custom-correlation-123"
        request = DocumentAnalysisRequest(
            file_id=sample_file_id,
            tenant_id=sample_tenant_id,
            correlation_id=correlation_id,
        )

        result = await process_document_use_case.execute(request)

        assert result.correlation_id == correlation_id
