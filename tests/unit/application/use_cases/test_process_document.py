"""Unit tests for ProcessDocumentUseCase."""

import asyncio
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
from src.core.entities.document import Document, ReplacedBlobReferences
from src.core.entities.document_analysis import (
    BlockKind,
    ContentBlock,
    ExtractedTable,
    ExtractionMetadata,
    MarkdownOutput,
    PageContent,
    TableCell,
    TableRow,
    TextSpan,
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
        document_extractor=mock_document_intelligence_adapter,
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
        # Verify output path is namespaced by tenant, file and run
        expected_output_prefix = text_prefix(sample_tenant_id, sample_file_id)
        assert call_args[1]["blob_path"].startswith(expected_output_prefix)

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
            document_extractor=mock_document_intelligence_adapter,
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
            document_extractor=mock_document_intelligence_adapter,
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
            document_extractor=mock_adapter,
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
            document_extractor=mock_adapter,
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
        document_extractor=adapter,
        pipeline_store=pipeline_store,
        persist_raw_analysis=persist_raw_analysis,
    )


def uploads_by_path(mock_blob_client: MagicMock) -> dict:
    """Index upload_blob calls by blob path."""
    return {call.kwargs["blob_path"]: call.kwargs for call in mock_blob_client.upload_blob.call_args_list}


def analysis_prefix(tenant_id: str, file_id: str) -> str:
    """Sidecars are written under a run-scoped path, so tests match the prefix."""
    return f"{tenant_id}/{file_id}/analysis/"


def text_prefix(tenant_id: str, file_id: str) -> str:
    """Text outputs are run-scoped for the same reason sidecars are."""
    return f"{tenant_id}/{file_id}/text/"


def text_uploads(mock_blob_client: MagicMock, tenant_id: str, file_id: str) -> dict:
    """The text uploads recorded for this document, keyed by their run-scoped path."""
    prefix = text_prefix(tenant_id, file_id)
    return {
        path: kwargs
        for path, kwargs in uploads_by_path(mock_blob_client).items()
        if path.startswith(prefix)
    }


def sidecar_uploads(mock_blob_client: MagicMock, tenant_id: str, file_id: str) -> dict:
    """The sidecar uploads recorded for this document, keyed by their run-scoped path."""
    prefix = analysis_prefix(tenant_id, file_id)
    return {
        path: kwargs
        for path, kwargs in uploads_by_path(mock_blob_client).items()
        if path.startswith(prefix)
    }


class TestTheCanonicalBlocksReachTextJson:
    """The stage stores what the adapter produced, including the block list.

    No logic in the use case changes for this — which is the point: the block list is part
    of the output model, so it serialises with everything else. This test exists so that a
    future change to how text.json is written cannot drop it silently.
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
    def output_with_blocks(self, sample_markdown_output: MarkdownOutput) -> MarkdownOutput:
        text = "# Heading\n\n<table>\n<tr><td>a</td></tr>\n</table>"
        table = ExtractedTable(
            row_count=1,
            column_count=1,
            cells=[TableCell(row_index=0, column_index=0, content="a")],
            rendered="<table>\n<tr><td>a</td></tr>\n</table>",
            render_prefix="<table>\n",
            rows=[TableRow(row_index=0, rendered="<tr><td>a</td></tr>\n", source_range=(19, 39))],
            render_suffix="</table>",
            spans=[TextSpan(offset=11, length=36)],
        )
        return sample_markdown_output.model_copy(
            update={
                "extracted_text": text,
                "raw_analysis": RAW_ANALYSIS,
                "tables": [table],
                "blocks": [
                    ContentBlock(kind=BlockKind.HEADING, start=0, end=9, role="title"),
                    ContentBlock(kind=BlockKind.TABLE, start=11, end=47, table_index=0),
                ],
            }
        )

    async def _text_json(self, use_case, request_, mock_blob_client, tenant_id, file_id) -> dict:
        await use_case.execute(request_)
        (written,) = text_uploads(mock_blob_client, tenant_id, file_id).values()
        return json.loads(written["data"])

    async def test_blocks_are_serialised_into_text_json(
        self,
        mock_blob_client,
        mock_document_intelligence_adapter,
        mock_pipeline_store,
        output_with_blocks,
        request_,
        sample_tenant_id,
        sample_file_id,
    ):
        use_case = build_use_case(
            mock_blob_client, mock_document_intelligence_adapter, mock_pipeline_store,
            output_with_blocks,
        )

        text_json = await self._text_json(
            use_case, request_, mock_blob_client, sample_tenant_id, sample_file_id
        )

        assert [block["kind"] for block in text_json["blocks"]] == ["heading", "table"]
        assert text_json["blocks"][0]["role"] == "title"
        assert text_json["blocks"][1]["table_index"] == 0

    async def test_stored_blocks_still_resolve_against_the_stored_text(
        self,
        mock_blob_client,
        mock_document_intelligence_adapter,
        mock_pipeline_store,
        output_with_blocks,
        request_,
        sample_tenant_id,
        sample_file_id,
    ):
        """The offset invariant has to survive storage to be worth anything downstream."""
        use_case = build_use_case(
            mock_blob_client, mock_document_intelligence_adapter, mock_pipeline_store,
            output_with_blocks,
        )

        text_json = await self._text_json(
            use_case, request_, mock_blob_client, sample_tenant_id, sample_file_id
        )
        restored = MarkdownOutput.model_validate(text_json)

        assert restored.blocks[0].text_in(restored.extracted_text) == "# Heading"
        assert restored.blocks[1].text_in(restored.extracted_text) == restored.tables[0].rendered
        assert restored.tables[0].fragment() == restored.tables[0].rendered

    async def test_the_raw_sidecar_is_untouched_by_any_of_this(
        self,
        mock_blob_client,
        mock_document_intelligence_adapter,
        mock_pipeline_store,
        output_with_blocks,
        request_,
        sample_tenant_id,
        sample_file_id,
    ):
        """The sidecar is the provider's response verbatim; the canonical model is separate."""
        use_case = build_use_case(
            mock_blob_client, mock_document_intelligence_adapter, mock_pipeline_store,
            output_with_blocks,
        )

        await use_case.execute(request_)

        (sidecar,) = sidecar_uploads(
            mock_blob_client, sample_tenant_id, sample_file_id
        ).values()
        assert json.loads(sidecar["data"]) == RAW_ANALYSIS


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

        sidecars = sidecar_uploads(mock_blob_client, sample_tenant_id, sample_file_id)
        assert len(sidecars) == 1
        (written,) = sidecars.values()
        assert written["container"] == "text"
        assert json.loads(written["data"]) == RAW_ANALYSIS

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
        sidecars = sidecar_uploads(mock_blob_client, sample_tenant_id, sample_file_id)
        # The recorded reference is the one path that can locate the sidecar.
        assert kwargs["analysis_blob_ref"] in sidecars
        assert kwargs["text_blob_ref"] in text_uploads(
            mock_blob_client, sample_tenant_id, sample_file_id
        )
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

        (text_written,) = text_uploads(
            mock_blob_client, sample_tenant_id, sample_file_id
        ).values()
        text_json = json.loads(text_written["data"])
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
        assert not sidecar_uploads(mock_blob_client, sample_tenant_id, sample_file_id)
        assert result.status == ProcessingStatus.COMPLETED
        kwargs = mock_pipeline_store.update_blob_references.call_args.kwargs
        assert kwargs["analysis_blob_ref"] is None
        # Not merely "leave it alone": a re-run must not inherit an earlier sidecar.
        assert kwargs["clear_analysis_blob_ref"] is True
        (text_written,) = text_uploads(
            mock_blob_client, sample_tenant_id, sample_file_id
        ).values()
        text_json = json.loads(text_written["data"])
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

        assert not sidecar_uploads(mock_blob_client, sample_tenant_id, sample_file_id)
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

        async def upload(container, blob_path, data, content_type=None, **kwargs):
            if blob_path.startswith(analysis_prefix(sample_tenant_id, sample_file_id)):
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
        (text_written,) = text_uploads(
            mock_blob_client, sample_tenant_id, sample_file_id
        ).values()
        assert json.loads(text_written["data"])["extraction_metadata"]["raw_analysis_stored"] is False

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

        (written,) = sidecar_uploads(mock_blob_client, sample_tenant_id, sample_file_id).values()
        assert "2026-01-01 12:00:00" in written["data"]


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
        # Reads see the references previous runs wrote, as they would from SQL. Without
        # this the double would hide the fact that a re-run is a re-run.
        document = self._doc.document.model_copy(
            update={
                "raw_blob_ref": self.raw_blob_ref,
                "text_blob_ref": self.text_blob_ref,
                "analysis_blob_ref": self.analysis_blob_ref,
            }
        )
        return self._doc.model_copy(update={"document": document})

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
        # explicit, and the update reports what it displaced. The SQL Server tests pin
        # that this mirror is faithful.
        replaced = ReplacedBlobReferences(
            text_blob_ref=self.text_blob_ref,
            analysis_blob_ref=self.analysis_blob_ref,
        )
        if raw_blob_ref is not None:
            self.raw_blob_ref = raw_blob_ref
        if text_blob_ref is not None:
            self.text_blob_ref = text_blob_ref
        if analysis_blob_ref is not None:
            self.analysis_blob_ref = analysis_blob_ref
        elif clear_analysis_blob_ref:
            self.analysis_blob_ref = None
        return replaced


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

        assert store.analysis_blob_ref is not None
        assert store.analysis_blob_ref.startswith(
            analysis_prefix(sample_tenant_id, sample_file_id)
        )

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

        async def upload(container, blob_path, data, content_type=None, **kwargs):
            if blob_path.startswith(analysis_prefix(sample_tenant_id, sample_file_id)):
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

        assert store.text_blob_ref.startswith(text_prefix(sample_tenant_id, sample_file_id))
        assert store.raw_blob_ref == sample_document_with_pipeline.document.raw_blob_ref


class FakeBlobContainer:
    """A blob container that keeps what was written, keyed by path.

    Fixed-path artefacts overwrite each other across runs, which is the whole reason a
    half-finished run can leave two files describing different extractions. Asserting on
    upload calls cannot see that; asserting on stored bytes can.
    """

    def __init__(self):
        self.blobs: dict[str, str] = {}
        self.fail_on: set[str] = set()
        self.fail_on_prefix: str | None = None
        self.deleted: list[str] = []

    async def upload_blob(self, container, blob_path, data, content_type=None, **kwargs):
        if blob_path in self.fail_on or (
            self.fail_on_prefix and blob_path.startswith(self.fail_on_prefix)
        ):
            raise RuntimeError(f"blob storage said no: {blob_path}")
        self.blobs[blob_path] = data
        return {"etag": "etag", "url": f"https://blob/{blob_path}"}

    async def delete_blob(self, container, blob_path):
        self.deleted.append(blob_path)
        return self.blobs.pop(blob_path, None) is not None

    async def download_blob(self, container, blob_path):
        return b"%PDF-1.4 fake pdf content"

    async def blob_exists(self, container, blob_path):
        return True


class TestACompletedRunSurvivesAFailedReprocess:
    """A run publishes both outputs at once, or publishes nothing at all.

    Every artefact a run writes is namespaced under that run, and the document row is the
    only way to reach any of it. Publication is the single update that moves both
    references together. So a run that fails anywhere before that update leaves the last
    completed extraction untouched — there is no window in which its text has been
    replaced but its raw analysis has not, and nothing to roll back.
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
    def blobs(self) -> FakeBlobContainer:
        return FakeBlobContainer()

    @pytest.fixture
    def store(self, sample_document_with_pipeline) -> StatefulBlobReferences:
        return StatefulBlobReferences(sample_document_with_pipeline)

    @staticmethod
    def _output(sample_markdown_output: MarkdownOutput, marker: str) -> MarkdownOutput:
        """An analysis output tagged so the run it came from is identifiable."""
        return sample_markdown_output.model_copy(
            update={
                "extracted_text": f"text from {marker}",
                "raw_analysis": {"modelId": "prebuilt-layout", "run": marker},
            }
        )

    async def _run(self, blobs, adapter, store, output, request_, persist=True):
        use_case = build_use_case(blobs, adapter, store, output, persist_raw_analysis=persist)
        return await use_case.execute(request_)

    async def _complete_first_run(
        self, blobs, adapter, store, sample_markdown_output, request_
    ):
        """Run once successfully and return the pair it published."""
        await self._run(
            blobs, adapter, store, self._output(sample_markdown_output, "run-1"), request_
        )
        return store.text_blob_ref, store.analysis_blob_ref

    @staticmethod
    def _assert_pair_is(blobs, store, text_ref, analysis_ref, marker):
        """Both references resolve, and both resolve to the same run."""
        assert store.text_blob_ref == text_ref
        assert store.analysis_blob_ref == analysis_ref
        assert json.loads(blobs.blobs[text_ref])["extracted_text"] == f"text from {marker}"
        assert json.loads(blobs.blobs[analysis_ref])["run"] == marker

    async def test_the_first_run_publishes_a_matched_pair(
        self, blobs, store, mock_document_intelligence_adapter, sample_markdown_output, request_
    ):
        text_ref, analysis_ref = await self._complete_first_run(
            blobs, mock_document_intelligence_adapter, store, sample_markdown_output, request_
        )

        self._assert_pair_is(blobs, store, text_ref, analysis_ref, "run-1")

    async def test_a_failed_text_write_leaves_the_completed_run_untouched(
        self,
        blobs,
        store,
        mock_document_intelligence_adapter,
        sample_markdown_output,
        request_,
        sample_tenant_id,
        sample_file_id,
    ):
        text_ref, analysis_ref = await self._complete_first_run(
            blobs, mock_document_intelligence_adapter, store, sample_markdown_output, request_
        )

        blobs.fail_on_prefix = text_prefix(sample_tenant_id, sample_file_id)
        with pytest.raises(DocumentProcessingError):
            await self._run(
                blobs,
                mock_document_intelligence_adapter,
                store,
                self._output(sample_markdown_output, "run-2"),
                request_,
            )

        self._assert_pair_is(blobs, store, text_ref, analysis_ref, "run-1")

    async def test_a_failed_publish_leaves_the_completed_run_untouched(
        self,
        blobs,
        store,
        mock_document_intelligence_adapter,
        sample_markdown_output,
        request_,
    ):
        """The case a fixed text path could not survive: a transient store outage.

        Both outputs of run 2 are written and then abandoned, because the references never
        moved. Run 1 is still published, still matched, still whole.
        """
        text_ref, analysis_ref = await self._complete_first_run(
            blobs, mock_document_intelligence_adapter, store, sample_markdown_output, request_
        )
        store.update_blob_references = AsyncMock(side_effect=RuntimeError("sql refused"))

        with pytest.raises(DocumentProcessingError):
            await self._run(
                blobs,
                mock_document_intelligence_adapter,
                store,
                self._output(sample_markdown_output, "run-2"),
                request_,
            )

        self._assert_pair_is(blobs, store, text_ref, analysis_ref, "run-1")

    async def test_an_abandoned_run_leaves_no_outputs_behind(
        self,
        blobs,
        store,
        mock_document_intelligence_adapter,
        sample_markdown_output,
        request_,
        sample_tenant_id,
        sample_file_id,
    ):
        """Nothing references run 2's outputs, so they are dropped rather than left to leak."""
        text_ref, analysis_ref = await self._complete_first_run(
            blobs, mock_document_intelligence_adapter, store, sample_markdown_output, request_
        )
        store.update_blob_references = AsyncMock(side_effect=RuntimeError("sql refused"))

        with pytest.raises(DocumentProcessingError):
            await self._run(
                blobs,
                mock_document_intelligence_adapter,
                store,
                self._output(sample_markdown_output, "run-2"),
                request_,
            )

        assert set(blobs.blobs) == {text_ref, analysis_ref}

    async def test_a_failed_first_run_leaves_nothing_behind(
        self,
        blobs,
        store,
        mock_document_intelligence_adapter,
        sample_markdown_output,
        request_,
        sample_tenant_id,
        sample_file_id,
    ):
        """No previous pair to protect, and no orphans either."""
        blobs.fail_on_prefix = text_prefix(sample_tenant_id, sample_file_id)

        with pytest.raises(DocumentProcessingError):
            await self._run(
                blobs,
                mock_document_intelligence_adapter,
                store,
                self._output(sample_markdown_output, "run-1"),
                request_,
            )

        assert blobs.blobs == {}
        assert store.text_blob_ref is None
        assert store.analysis_blob_ref is None

    async def test_the_completed_run_survives_a_cleanup_delete_that_also_fails(
        self,
        blobs,
        store,
        mock_document_intelligence_adapter,
        sample_markdown_output,
        request_,
    ):
        """Tidying up is best-effort; the real error is what has to surface."""
        text_ref, analysis_ref = await self._complete_first_run(
            blobs, mock_document_intelligence_adapter, store, sample_markdown_output, request_
        )
        store.update_blob_references = AsyncMock(side_effect=RuntimeError("sql refused"))
        blobs.delete_blob = AsyncMock(side_effect=RuntimeError("delete refused"))

        with pytest.raises(DocumentProcessingError) as exc_info:
            await self._run(
                blobs,
                mock_document_intelligence_adapter,
                store,
                self._output(sample_markdown_output, "run-2"),
                request_,
            )

        assert "sql refused" in str(exc_info.value)
        # The leaked blobs are unreachable: the references never moved off run 1.
        self._assert_pair_is(blobs, store, text_ref, analysis_ref, "run-1")

    async def test_a_successful_reprocess_replaces_the_pair_and_sweeps_the_old_one(
        self, blobs, store, mock_document_intelligence_adapter, sample_markdown_output, request_
    ):
        """Run-scoped paths must not accumulate a pair per run forever."""
        first_text, first_analysis = await self._complete_first_run(
            blobs, mock_document_intelligence_adapter, store, sample_markdown_output, request_
        )

        await self._run(
            blobs,
            mock_document_intelligence_adapter,
            store,
            self._output(sample_markdown_output, "run-2"),
            request_,
        )

        self._assert_pair_is(
            blobs, store, store.text_blob_ref, store.analysis_blob_ref, "run-2"
        )
        assert first_text not in blobs.blobs
        assert first_analysis not in blobs.blobs

    async def test_a_reprocess_without_a_sidecar_sweeps_the_previous_pair(
        self, blobs, store, mock_document_intelligence_adapter, sample_markdown_output, request_
    ):
        """Its text is gone, so the old raw analysis can no longer be paired with anything."""
        first_text, first_analysis = await self._complete_first_run(
            blobs, mock_document_intelligence_adapter, store, sample_markdown_output, request_
        )

        await self._run(
            blobs,
            mock_document_intelligence_adapter,
            store,
            self._output(sample_markdown_output, "run-2"),
            request_,
            persist=False,
        )

        assert store.analysis_blob_ref is None
        assert json.loads(blobs.blobs[store.text_blob_ref])["extracted_text"] == "text from run-2"
        assert first_text not in blobs.blobs
        assert first_analysis not in blobs.blobs


class TestConcurrentExtractionsOfTheSameDocument:
    """Overlapping runs must never publish half of one run beside half of another.

    Two extractions of the same document can be in flight at once — the pipeline does not
    serialise them. Because each run writes under its own namespace and publishes both
    references in a single update, whichever run commits last wins *both* columns, and the
    row always names a text output and a raw analysis from the same run.
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
    def blobs(self) -> FakeBlobContainer:
        return FakeBlobContainer()

    @pytest.fixture
    def store(self, sample_document_with_pipeline) -> StatefulBlobReferences:
        return StatefulBlobReferences(sample_document_with_pipeline)

    @staticmethod
    def _output(sample_markdown_output: MarkdownOutput, marker: str) -> MarkdownOutput:
        return sample_markdown_output.model_copy(
            update={
                "extracted_text": f"text from {marker}",
                "raw_analysis": {"modelId": "prebuilt-layout", "run": marker},
            }
        )

    async def test_interleaved_runs_publish_a_matched_pair(
        self,
        blobs,
        store,
        mock_document_intelligence_adapter,
        sample_markdown_output,
        request_,
    ):
        """Force the worst interleaving: A writes its outputs, B runs to completion, A publishes."""
        b_has_published = asyncio.Event()
        a_has_written_outputs = asyncio.Event()
        commit_order: list[str] = []

        real_update = store.update_blob_references

        def marker_of(text_ref: str) -> str:
            return json.loads(blobs.blobs[text_ref])["extracted_text"].removeprefix("text from ")

        async def update_blob_references(*args, **kwargs):
            marker = marker_of(kwargs["text_blob_ref"])
            if marker == "run-a":
                # A reaches the publication point first, then stalls until B is done —
                # the interleaving a non-atomic publish would tear apart.
                await b_has_published.wait()
            await real_update(*args, **kwargs)
            commit_order.append(marker)
            if marker == "run-b":
                b_has_published.set()

        store.update_blob_references = update_blob_references

        original_upload = blobs.upload_blob

        async def upload_blob(container, blob_path, data, content_type=None, **kwargs):
            result = await original_upload(container, blob_path, data, content_type, **kwargs)
            if "run-a" in str(data) and blob_path.startswith(
                text_prefix(request_.tenant_id, request_.file_id)
            ):
                a_has_written_outputs.set()
            return result

        blobs.upload_blob = upload_blob

        async def run(marker: str, wait_for_a: bool):
            if wait_for_a:
                await a_has_written_outputs.wait()
            use_case = build_use_case(
                blobs,
                mock_document_intelligence_adapter,
                store,
                self._output(sample_markdown_output, marker),
                persist_raw_analysis=True,
            )
            return await use_case.execute(request_)

        await asyncio.gather(run("run-a", False), run("run-b", True))

        # The interleaving really happened: B committed while A was mid-publish.
        assert commit_order == ["run-b", "run-a"]

        # And the row names one run's text beside that same run's raw analysis.
        published_text = json.loads(blobs.blobs[store.text_blob_ref])["extracted_text"]
        published_analysis = json.loads(blobs.blobs[store.analysis_blob_ref])["run"]
        assert published_text == f"text from {published_analysis}"
        assert published_analysis == "run-a"

    async def test_the_losing_run_leaves_nothing_behind(
        self,
        blobs,
        store,
        mock_document_intelligence_adapter,
        sample_markdown_output,
        request_,
    ):
        """B publishes, then A publishes over it. B's outputs must not leak.

        Each run sweeps what its own publish displaced, reported by the update itself. A
        run that swept what it saw before starting would delete the outputs both runs
        observed — twice — and never touch the pair the other run published in between.
        """
        b_has_published = asyncio.Event()
        a_has_written_outputs = asyncio.Event()
        real_update = store.update_blob_references

        async def update_blob_references(*args, **kwargs):
            marker = json.loads(blobs.blobs[kwargs["text_blob_ref"]])["extracted_text"]
            if marker.endswith("run-a"):
                await b_has_published.wait()
            replaced = await real_update(*args, **kwargs)
            if marker.endswith("run-b"):
                b_has_published.set()
            return replaced

        store.update_blob_references = update_blob_references

        original_upload = blobs.upload_blob

        async def upload_blob(container, blob_path, data, content_type=None, **kwargs):
            result = await original_upload(container, blob_path, data, content_type, **kwargs)
            if "run-a" in str(data) and blob_path.startswith(
                text_prefix(request_.tenant_id, request_.file_id)
            ):
                a_has_written_outputs.set()
            return result

        blobs.upload_blob = upload_blob

        async def run(marker: str, wait_for_a: bool):
            if wait_for_a:
                await a_has_written_outputs.wait()
            use_case = build_use_case(
                blobs,
                mock_document_intelligence_adapter,
                store,
                self._output(sample_markdown_output, marker),
                persist_raw_analysis=True,
            )
            return await use_case.execute(request_)

        await asyncio.gather(run("run-a", False), run("run-b", True))

        # Only the published pair survives: run B's outputs, displaced by A, are gone.
        assert set(blobs.blobs) == {store.text_blob_ref, store.analysis_blob_ref}
