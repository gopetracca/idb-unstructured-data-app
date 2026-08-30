"""Unit tests for ProcessDocumentUseCase."""

import json
from datetime import datetime
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

pytestmark = pytest.mark.unit


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


RAW_ANALYSIS = {
    "apiVersion": "2024-11-30",
    "modelId": "prebuilt-layout",
    "tables": [{"rowCount": 2, "columnCount": 2, "cells": [{"rowIndex": 0, "columnIndex": 0}]}],
    "fieldFromTheFuture": {"nested": [1, 2]},
}


@pytest.fixture
def markdown_output_with_raw(sample_markdown_output: MarkdownOutput) -> MarkdownOutput:
    """An analysis output that carries a verbatim service response."""
    return sample_markdown_output.model_copy(update={"raw_analysis": RAW_ANALYSIS})


def build_use_case(
    blob_client,
    adapter,
    pipeline_store,
    output: MarkdownOutput,
    persist_raw_analysis: bool = True,
) -> ProcessDocumentUseCase:
    """Wire a use case whose adapter returns `output`."""
    adapter.analyze_document = AsyncMock(return_value=output)
    return ProcessDocumentUseCase(
        blob_client=blob_client,
        document_intelligence=adapter,
        pipeline_store=pipeline_store,
        persist_raw_analysis=persist_raw_analysis,
    )


def uploads_by_path(mock_blob_client: MagicMock) -> dict:
    """Index upload_blob calls by blob path."""
    return {call.kwargs["blob_path"]: call.kwargs for call in mock_blob_client.upload_blob.call_args_list}


class TestRawAnalysisPersistence:
    """The verbatim service response is stored beside the extracted text."""

    @pytest.fixture
    def request_(self, sample_file_id: str, sample_tenant_id: str) -> DocumentAnalysisRequest:
        return DocumentAnalysisRequest(
            file_id=sample_file_id,
            tenant_id=sample_tenant_id,
            source_container="raw",
            output_container="text",
        )

    async def test_analysis_json_is_written_verbatim(
        self,
        mock_blob_client,
        mock_document_intelligence_adapter,
        mock_pipeline_store,
        markdown_output_with_raw,
        request_,
        sample_file_id,
        sample_tenant_id,
    ):
        use_case = build_use_case(
            mock_blob_client,
            mock_document_intelligence_adapter,
            mock_pipeline_store,
            markdown_output_with_raw,
        )

        await use_case.execute(request_)

        path = f"{sample_tenant_id}/{sample_file_id}/analysis.json"
        uploads = uploads_by_path(mock_blob_client)
        assert path in uploads
        assert uploads[path]["container"] == "text"
        assert json.loads(uploads[path]["data"]) == RAW_ANALYSIS

    async def test_analysis_blob_ref_is_recorded(
        self,
        mock_blob_client,
        mock_document_intelligence_adapter,
        mock_pipeline_store,
        markdown_output_with_raw,
        request_,
        sample_file_id,
        sample_tenant_id,
    ):
        """Blob references in SQL are the source of truth, so the path gets recorded."""
        use_case = build_use_case(
            mock_blob_client,
            mock_document_intelligence_adapter,
            mock_pipeline_store,
            markdown_output_with_raw,
        )

        await use_case.execute(request_)

        kwargs = mock_pipeline_store.update_blob_references.call_args.kwargs
        assert kwargs["analysis_blob_ref"] == f"{sample_tenant_id}/{sample_file_id}/analysis.json"
        assert kwargs["text_blob_ref"] == f"{sample_tenant_id}/{sample_file_id}/text.json"
        assert kwargs["clear_analysis_blob_ref"] is False

    async def test_text_json_records_that_the_raw_copy_landed(
        self,
        mock_blob_client,
        mock_document_intelligence_adapter,
        mock_pipeline_store,
        markdown_output_with_raw,
        request_,
        sample_tenant_id,
        sample_file_id,
    ):
        use_case = build_use_case(
            mock_blob_client,
            mock_document_intelligence_adapter,
            mock_pipeline_store,
            markdown_output_with_raw,
        )

        await use_case.execute(request_)

        text_json = json.loads(
            uploads_by_path(mock_blob_client)[f"{sample_tenant_id}/{sample_file_id}/text.json"]["data"]
        )
        assert text_json["extraction_metadata"]["raw_analysis_stored"] is True
        # The raw copy lives in analysis.json, not duplicated into text.json.
        assert "raw_analysis" not in text_json

    async def test_persistence_can_be_disabled(
        self,
        mock_blob_client,
        mock_document_intelligence_adapter,
        mock_pipeline_store,
        markdown_output_with_raw,
        request_,
        sample_tenant_id,
        sample_file_id,
    ):
        """DOCUMENT_INTELLIGENCE_PERSIST_RAW_RESULT=false suppresses only the sidecar."""
        use_case = build_use_case(
            mock_blob_client,
            mock_document_intelligence_adapter,
            mock_pipeline_store,
            markdown_output_with_raw,
            persist_raw_analysis=False,
        )

        result = await use_case.execute(request_)

        uploads = uploads_by_path(mock_blob_client)
        assert f"{sample_tenant_id}/{sample_file_id}/analysis.json" not in uploads
        assert result.status == ProcessingStatus.COMPLETED
        kwargs = mock_pipeline_store.update_blob_references.call_args.kwargs
        assert kwargs["analysis_blob_ref"] is None
        # Not merely "leave it alone": a re-run must not inherit an earlier sidecar.
        assert kwargs["clear_analysis_blob_ref"] is True
        text_json = json.loads(uploads[f"{sample_tenant_id}/{sample_file_id}/text.json"]["data"])
        assert text_json["extraction_metadata"]["raw_analysis_stored"] is False
        # The structural elements are not gated by the setting.
        assert "tables" in text_json

    async def test_adapter_without_a_raw_payload_writes_no_sidecar(
        self,
        mock_blob_client,
        mock_document_intelligence_adapter,
        mock_pipeline_store,
        sample_markdown_output,
        request_,
        sample_tenant_id,
        sample_file_id,
    ):
        """The fake adapter has no service response to copy."""
        use_case = build_use_case(
            mock_blob_client,
            mock_document_intelligence_adapter,
            mock_pipeline_store,
            sample_markdown_output,
        )

        result = await use_case.execute(request_)

        assert f"{sample_tenant_id}/{sample_file_id}/analysis.json" not in uploads_by_path(
            mock_blob_client
        )
        assert result.status == ProcessingStatus.COMPLETED
        assert (
            mock_pipeline_store.update_blob_references.call_args.kwargs[
                "clear_analysis_blob_ref"
            ]
            is True
        )

    async def test_a_failed_sidecar_write_does_not_fail_the_stage(
        self,
        mock_blob_client,
        mock_document_intelligence_adapter,
        mock_pipeline_store,
        markdown_output_with_raw,
        request_,
        sample_tenant_id,
        sample_file_id,
    ):
        """text.json is the pipeline's contract; losing the sidecar only degrades fidelity."""
        text_path = f"{sample_tenant_id}/{sample_file_id}/text.json"
        analysis_path = f"{sample_tenant_id}/{sample_file_id}/analysis.json"

        async def upload(container, blob_path, data, content_type=None, **kwargs):
            if blob_path == analysis_path:
                raise RuntimeError("blob storage said no")
            return f"https://blob/{blob_path}"

        mock_blob_client.upload_blob = AsyncMock(side_effect=upload)

        use_case = build_use_case(
            mock_blob_client,
            mock_document_intelligence_adapter,
            mock_pipeline_store,
            markdown_output_with_raw,
        )

        result = await use_case.execute(request_)

        assert result.status == ProcessingStatus.COMPLETED
        kwargs = mock_pipeline_store.update_blob_references.call_args.kwargs
        assert kwargs["analysis_blob_ref"] is None
        assert kwargs["clear_analysis_blob_ref"] is True
        written = [c.kwargs["data"] for c in mock_blob_client.upload_blob.call_args_list
                   if c.kwargs["blob_path"] == text_path]
        assert json.loads(written[0])["extraction_metadata"]["raw_analysis_stored"] is False

    async def test_raw_payload_with_a_datetime_still_serialises(
        self,
        mock_blob_client,
        mock_document_intelligence_adapter,
        mock_pipeline_store,
        sample_markdown_output,
        request_,
        sample_tenant_id,
        sample_file_id,
    ):
        """A value json cannot encode natively must not cost us the copy."""
        output = sample_markdown_output.model_copy(
            update={"raw_analysis": {"createdDateTime": datetime(2026, 1, 1, 12, 0)}}
        )
        use_case = build_use_case(
            mock_blob_client, mock_document_intelligence_adapter, mock_pipeline_store, output
        )

        await use_case.execute(request_)

        data = uploads_by_path(mock_blob_client)[
            f"{sample_tenant_id}/{sample_file_id}/analysis.json"
        ]["data"]
        assert "2026-01-01 12:00:00" in data


class StatefulBlobReferences:
    """A pipeline store that remembers references, like the real one does.

    The mocks elsewhere in this file assert on call arguments, which cannot show what a
    *second* run does to a row the first run wrote. This keeps the state so reprocessing
    can be tested as the sequence it actually is.
    """

    def __init__(self, doc):
        self._doc = doc
        self.raw_blob_ref = doc.document.raw_blob_ref
        self.text_blob_ref = None
        self.analysis_blob_ref = None

    async def get_by_id(self, tenant_id, file_id):
        return self._doc

    async def mark_processing(self, *args, **kwargs):
        return self._doc.pipeline

    async def mark_failed(self, *args, **kwargs):
        return self._doc.pipeline

    async def update_blob_references(
        self,
        tenant_id,
        file_id,
        raw_blob_ref=None,
        text_blob_ref=None,
        analysis_blob_ref=None,
        clear_analysis_blob_ref=False,
    ):
        # Mirrors DocumentRepositorySQLServer: None means "leave alone", clearing is
        # explicit. The SQL Server tests pin that this mirror is faithful.
        if raw_blob_ref is not None:
            self.raw_blob_ref = raw_blob_ref
        if text_blob_ref is not None:
            self.text_blob_ref = text_blob_ref
        if analysis_blob_ref is not None:
            self.analysis_blob_ref = analysis_blob_ref
        elif clear_analysis_blob_ref:
            self.analysis_blob_ref = None


class TestReprocessingADocumentThatAlreadyHasASidecar:
    """The case that motivated the explicit clear.

    A document extracted once with a sidecar, then re-extracted without one, must not keep
    pointing at the first run's analysis.json: that file describes the earlier content,
    and the text.json now beside it says `raw_analysis_stored: false`.
    """

    @pytest.fixture
    def request_(self, sample_file_id: str, sample_tenant_id: str) -> DocumentAnalysisRequest:
        return DocumentAnalysisRequest(
            file_id=sample_file_id,
            tenant_id=sample_tenant_id,
            source_container="raw",
            output_container="text",
        )

    @pytest.fixture
    def store(self, sample_document_with_pipeline) -> StatefulBlobReferences:
        return StatefulBlobReferences(sample_document_with_pipeline)

    async def _run(
        self, store, blob_client, adapter, output, request_, persist: bool
    ):
        use_case = build_use_case(
            blob_client, adapter, store, output, persist_raw_analysis=persist
        )
        return await use_case.execute(request_)

    async def test_first_run_records_the_reference(
        self,
        store,
        mock_blob_client,
        mock_document_intelligence_adapter,
        markdown_output_with_raw,
        request_,
        sample_tenant_id,
        sample_file_id,
    ):
        await self._run(
            store,
            mock_blob_client,
            mock_document_intelligence_adapter,
            markdown_output_with_raw,
            request_,
            persist=True,
        )

        assert store.analysis_blob_ref == f"{sample_tenant_id}/{sample_file_id}/analysis.json"

    async def test_reprocessing_with_persistence_disabled_clears_the_reference(
        self,
        store,
        mock_blob_client,
        mock_document_intelligence_adapter,
        markdown_output_with_raw,
        request_,
    ):
        await self._run(
            store,
            mock_blob_client,
            mock_document_intelligence_adapter,
            markdown_output_with_raw,
            request_,
            persist=True,
        )
        assert store.analysis_blob_ref is not None

        await self._run(
            store,
            mock_blob_client,
            mock_document_intelligence_adapter,
            markdown_output_with_raw,
            request_,
            persist=False,
        )

        assert store.analysis_blob_ref is None

    async def test_reprocessing_with_a_failing_sidecar_write_clears_the_reference(
        self,
        store,
        mock_blob_client,
        mock_document_intelligence_adapter,
        markdown_output_with_raw,
        request_,
        sample_tenant_id,
        sample_file_id,
    ):
        await self._run(
            store,
            mock_blob_client,
            mock_document_intelligence_adapter,
            markdown_output_with_raw,
            request_,
            persist=True,
        )
        assert store.analysis_blob_ref is not None

        analysis_path = f"{sample_tenant_id}/{sample_file_id}/analysis.json"

        async def upload(container, blob_path, data, content_type=None, **kwargs):
            if blob_path == analysis_path:
                raise RuntimeError("blob storage said no")
            return f"https://blob/{blob_path}"

        mock_blob_client.upload_blob = AsyncMock(side_effect=upload)

        result = await self._run(
            store,
            mock_blob_client,
            mock_document_intelligence_adapter,
            markdown_output_with_raw,
            request_,
            persist=True,
        )

        assert result.status == ProcessingStatus.COMPLETED
        assert store.analysis_blob_ref is None

    async def test_reprocessing_still_updates_the_text_reference(
        self,
        store,
        mock_blob_client,
        mock_document_intelligence_adapter,
        markdown_output_with_raw,
        request_,
        sample_document_with_pipeline,
        sample_tenant_id,
        sample_file_id,
    ):
        """Clearing one reference must not disturb the others."""
        await self._run(
            store,
            mock_blob_client,
            mock_document_intelligence_adapter,
            markdown_output_with_raw,
            request_,
            persist=False,
        )

        assert store.text_blob_ref == f"{sample_tenant_id}/{sample_file_id}/text.json"
        assert store.raw_blob_ref == sample_document_with_pipeline.document.raw_blob_ref
