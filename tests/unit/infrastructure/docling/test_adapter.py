"""The Docling adapter's own behaviour: what it refuses, and what it does with a result.

The conversion is Docling's; what belongs to this adapter is the layer around it — the
limits it applies before any model runs, its refusal to publish an incomplete conversion,
and the failure it raises when a deployment asks for offline artifacts it does not have.
All of that is testable with a stub converter, so none of these tests need model weights.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("docling", reason="the optional docling extra is not installed")

from src.config.settings import DoclingSettings
from src.core.errors import DocumentProcessingError, UnsupportedFormatError
from src.infrastructure.docling.adapter import DoclingExtractionAdapter
from tests.support.docling_documents import build_sample_document

pytestmark = pytest.mark.unit


def _result(status: str = "success"):
    """A stand-in for `ConversionResult`, carrying a document the mapper can read."""
    return SimpleNamespace(
        status=SimpleNamespace(value=status),
        document=build_sample_document(),
        errors=[],
        confidence=None,
    )


def _adapter(converter=None, **overrides) -> DoclingExtractionAdapter:
    return DoclingExtractionAdapter(
        settings=DoclingSettings(**overrides),
        converter=converter or MagicMock(convert=MagicMock(return_value=_result())),
    )


class TestAdmissionControl:
    """Work it cannot finish is refused before a model runs — the only free bound."""

    async def test_an_oversized_document_is_refused_before_conversion(self):
        converter = MagicMock()
        adapter = _adapter(converter, max_file_size_bytes=10)

        with pytest.raises(DocumentProcessingError) as failure:
            await adapter.analyze_document(b"x" * 11, "application/pdf", "big")

        assert failure.value.details["reason"] == "file_size_limit_exceeded"
        converter.convert.assert_not_called()

    async def test_the_page_limit_is_handed_to_docling_to_apply_as_it_opens_the_file(self):
        """Counting pages ourselves would mean parsing the document twice."""
        converter = MagicMock(convert=MagicMock(return_value=_result()))
        adapter = _adapter(converter, max_pages=7)

        await adapter.analyze_document(b"%PDF-1.4", "application/pdf", "doc")

        assert converter.convert.call_args.kwargs["max_num_pages"] == 7

    async def test_an_unsupported_content_type_is_refused(self):
        adapter = _adapter()

        with pytest.raises(UnsupportedFormatError):
            await adapter.analyze_document(b"...", "application/zip", "doc")


class TestIncompleteConversions:
    @pytest.mark.parametrize("status", ["partial_success", "failure", "skipped"])
    async def test_anything_short_of_success_fails_the_stage(self, status):
        """Partial success is truncated text, and publishing it would index a document on
        content that silently stops partway."""
        converter = MagicMock(convert=MagicMock(return_value=_result(status)))
        adapter = _adapter(converter)

        with pytest.raises(DocumentProcessingError) as failure:
            await adapter.analyze_document(b"%PDF-1.4", "application/pdf", "doc")

        assert failure.value.details["reason"] == "conversion_incomplete"
        assert failure.value.details["status"] == status

    async def test_an_exception_from_docling_becomes_a_stage_failure(self):
        converter = MagicMock(convert=MagicMock(side_effect=RuntimeError("boom")))
        adapter = _adapter(converter)

        with pytest.raises(DocumentProcessingError) as failure:
            await adapter.analyze_document(b"%PDF-1.4", "application/pdf", "doc")

        assert failure.value.details["reason"] == "conversion_failed"
        assert failure.value.stage == "convert"


class TestModelArtifacts:
    async def test_a_configured_path_that_holds_no_artifacts_fails_at_construction(
        self, tmp_path
    ):
        """Where an egress-restricted container would otherwise hang on a blocked download
        inside a queue trigger, and have its message redelivered."""
        with pytest.raises(DocumentProcessingError) as failure:
            DoclingExtractionAdapter(
                settings=DoclingSettings(artifacts_path=str(tmp_path / "absent"))
            )

        assert "DOCLING_ARTIFACTS_PATH" in str(failure.value)
        assert failure.value.details["reason"] == "missing_model_artifacts"

    async def test_an_empty_directory_is_not_a_set_of_artifacts(self, tmp_path):
        with pytest.raises(DocumentProcessingError):
            DoclingExtractionAdapter(settings=DoclingSettings(artifacts_path=str(tmp_path)))


class TestSupportedFormats:
    def test_the_formats_are_doclings_and_not_the_azure_adapters(self):
        formats = _adapter().get_supported_formats()

        assert "application/pdf" in formats
        # Docling reads these; Document Intelligence does not, which is why the
        # capabilities endpoints report the configured engine rather than a fixed list.
        assert "text/html" in formats
        assert (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            in formats
        )

    async def test_the_content_type_decides_the_name_docling_infers_the_format_from(self):
        """The caller already knows what it has; a name Docling can trust beats a sniff."""
        converter = MagicMock(convert=MagicMock(return_value=_result()))
        adapter = _adapter(converter)

        await adapter.analyze_document(b"PK\x03\x04", "text/html", "doc-7")

        assert converter.convert.call_args.args[0].name == "doc-7.html"


class TestTheResultItReturns:
    async def test_it_carries_the_file_identity_it_was_given(self):
        adapter = _adapter()

        output = await adapter.analyze_document(
            b"%PDF-1.4", "application/pdf", "doc-9", file_version=3
        )

        assert (output.file_id, output.file_version) == ("doc-9", 3)

    async def test_it_names_docling_as_the_engine_and_reports_its_version(self):
        adapter = _adapter()

        output = await adapter.analyze_document(b"%PDF-1.4", "application/pdf", "doc")

        assert output.extraction_metadata.extraction_method == "docling"
        assert output.extraction_metadata.api_version
