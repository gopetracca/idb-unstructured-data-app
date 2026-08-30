"""Unit tests for FakeDocumentIntelligenceAdapter."""

import pytest

from src.core.errors import DocumentProcessingError, UnsupportedFormatError
from src.infrastructure.azure.adapters.document_intelligence_fake import (
    FakeDocumentIntelligenceAdapter,
)
from tests.support.table_reconstruction import assert_cells_tile_grid, assert_spans_resolve

pytestmark = pytest.mark.unit


class TestFakeDocumentIntelligenceAdapter:
    """Tests for FakeDocumentIntelligenceAdapter."""

    def test_get_supported_formats(
        self, fake_document_intelligence_adapter: FakeDocumentIntelligenceAdapter
    ):
        """Test getting supported formats."""
        formats = fake_document_intelligence_adapter.get_supported_formats()

        assert isinstance(formats, list)
        assert len(formats) > 0
        assert "application/pdf" in formats
        assert "image/png" in formats
        assert "image/jpeg" in formats
        assert "text/plain" in formats

    def test_is_format_supported_pdf(
        self, fake_document_intelligence_adapter: FakeDocumentIntelligenceAdapter
    ):
        """Test PDF format is supported."""
        assert fake_document_intelligence_adapter.is_format_supported("application/pdf")

    def test_is_format_supported_images(
        self, fake_document_intelligence_adapter: FakeDocumentIntelligenceAdapter
    ):
        """Test image formats are supported."""
        assert fake_document_intelligence_adapter.is_format_supported("image/png")
        assert fake_document_intelligence_adapter.is_format_supported("image/jpeg")
        assert fake_document_intelligence_adapter.is_format_supported("image/tiff")

    def test_is_format_supported_text(
        self, fake_document_intelligence_adapter: FakeDocumentIntelligenceAdapter
    ):
        """Test text format is supported."""
        assert fake_document_intelligence_adapter.is_format_supported("text/plain")

    def test_is_format_supported_unsupported(
        self, fake_document_intelligence_adapter: FakeDocumentIntelligenceAdapter
    ):
        """Test unsupported formats return False."""
        assert not fake_document_intelligence_adapter.is_format_supported(
            "application/unknown"
        )
        assert not fake_document_intelligence_adapter.is_format_supported("video/mp4")

    async def test_analyze_document_text_plain(
        self,
        fake_document_intelligence_adapter: FakeDocumentIntelligenceAdapter,
        sample_file_id: str,
    ):
        """Test analyzing plain text document."""
        content = b"Hello, this is a test document with some text content."

        result = await fake_document_intelligence_adapter.analyze_document(
            document_content=content,
            content_type="text/plain",
            file_id=sample_file_id,
            file_version=1,
        )

        assert result.file_id == sample_file_id
        assert result.file_version == 1
        assert "Hello" in result.extracted_text
        assert len(result.pages) == 1
        assert result.extraction_metadata.page_count == 1
        assert result.extraction_metadata.word_count > 0
        assert result.extraction_metadata.extraction_method == "fake-document-intelligence"

    async def test_analyze_document_pdf(
        self,
        fake_document_intelligence_adapter: FakeDocumentIntelligenceAdapter,
        sample_file_id: str,
    ):
        """Test analyzing PDF document returns placeholder content."""
        content = b"%PDF-1.4 fake pdf content"

        result = await fake_document_intelligence_adapter.analyze_document(
            document_content=content,
            content_type="application/pdf",
            file_id=sample_file_id,
            file_version=1,
        )

        assert result.file_id == sample_file_id
        assert "PDF document" in result.extracted_text or "Simulated" in result.extracted_text
        assert len(result.pages) >= 1

    async def test_analyze_document_image(
        self,
        fake_document_intelligence_adapter: FakeDocumentIntelligenceAdapter,
        sample_file_id: str,
    ):
        """Test analyzing image document returns placeholder content."""
        content = b"\x89PNG\r\n\x1a\n fake image content"

        result = await fake_document_intelligence_adapter.analyze_document(
            document_content=content,
            content_type="image/png",
            file_id=sample_file_id,
            file_version=1,
        )

        assert result.file_id == sample_file_id
        assert result.extracted_text is not None
        assert result.extraction_metadata.page_count >= 1

    async def test_analyze_document_unsupported_format(
        self,
        fake_document_intelligence_adapter: FakeDocumentIntelligenceAdapter,
        sample_file_id: str,
    ):
        """Test analyzing unsupported format raises error."""
        content = b"some content"

        with pytest.raises(UnsupportedFormatError) as exc_info:
            await fake_document_intelligence_adapter.analyze_document(
                document_content=content,
                content_type="application/unknown",
                file_id=sample_file_id,
            )

        assert "application/unknown" in exc_info.value.content_type
        assert len(exc_info.value.supported_formats) > 0

    async def test_analyze_document_returns_correct_metadata(
        self,
        fake_document_intelligence_adapter: FakeDocumentIntelligenceAdapter,
        sample_file_id: str,
    ):
        """Test that extraction metadata is properly set."""
        content = b"Word one two three four five six seven eight nine ten."

        result = await fake_document_intelligence_adapter.analyze_document(
            document_content=content,
            content_type="text/plain",
            file_id=sample_file_id,
        )

        assert result.extraction_metadata.page_count >= 1
        assert result.extraction_metadata.word_count > 0
        assert result.extraction_metadata.extraction_confidence == 0.95
        assert result.extraction_metadata.api_version == "fake-1.0.0"

    async def test_analyze_document_page_content(
        self,
        fake_document_intelligence_adapter: FakeDocumentIntelligenceAdapter,
        sample_file_id: str,
    ):
        """Test that page content is properly extracted."""
        content = b"This is page content with multiple words for testing."

        result = await fake_document_intelligence_adapter.analyze_document(
            document_content=content,
            content_type="text/plain",
            file_id=sample_file_id,
        )

        assert len(result.pages) >= 1
        page = result.pages[0]
        assert page.page_number == 1
        assert len(page.text) > 0
        assert page.word_count > 0

    async def test_analyze_document_with_file_version(
        self,
        fake_document_intelligence_adapter: FakeDocumentIntelligenceAdapter,
        sample_file_id: str,
    ):
        """Test that file_version is properly passed through."""
        content = b"Test content"

        result = await fake_document_intelligence_adapter.analyze_document(
            document_content=content,
            content_type="text/plain",
            file_id=sample_file_id,
            file_version=5,
        )

        assert result.file_version == 5

    def test_simulated_confidence_configuration(self):
        """Test that simulated confidence can be configured."""
        adapter = FakeDocumentIntelligenceAdapter(
            simulated_delay_seconds=0.01,
            simulated_confidence=0.85,
        )

        assert adapter._confidence == 0.85

    async def test_markdown_output_has_created_at(
        self,
        fake_document_intelligence_adapter: FakeDocumentIntelligenceAdapter,
        sample_file_id: str,
    ):
        """Test that output includes created_at timestamp."""
        content = b"Test content"

        result = await fake_document_intelligence_adapter.analyze_document(
            document_content=content,
            content_type="text/plain",
            file_id=sample_file_id,
        )

        assert result.created_at is not None

    async def test_analyze_document_handles_unicode(
        self,
        fake_document_intelligence_adapter: FakeDocumentIntelligenceAdapter,
        sample_file_id: str,
    ):
        """Test handling of unicode content."""
        content = "Hello 世界 🌍 émojis and spëcial çharacters".encode("utf-8")

        result = await fake_document_intelligence_adapter.analyze_document(
            document_content=content,
            content_type="text/plain",
            file_id=sample_file_id,
        )

        assert "世界" in result.extracted_text
        assert "émojis" in result.extracted_text


class TestFakeAdapterStructuralParity:
    """The fake emits the same enriched shape as the real adapter.

    Without this, `DOCUMENT_INTELLIGENCE_USE_FAKE=true` would give local runs and tests a
    document with no structure at all — and the table-handling code downstream would have
    nothing to run against until it reached Azure.
    """

    async def test_fake_emits_a_reconstructible_table(
        self, fake_document_intelligence_adapter, sample_file_id
    ):
        result = await fake_document_intelligence_adapter.analyze_document(
            document_content=b"Report title\n\nBody paragraph.",
            content_type="text/plain",
            file_id=sample_file_id,
        )

        assert len(result.tables) == 1
        table = result.tables[0]
        assert_cells_tile_grid(table)
        assert table.to_grid() == [
            ["Simulated Table", "Simulated Table"],
            ["Field", "Value"],
            ["File ID", sample_file_id],
        ]

    async def test_fake_table_has_a_header_row_and_a_merged_cell(
        self, fake_document_intelligence_adapter, sample_file_id
    ):
        """The two cases rendered markdown alone cannot round-trip."""
        result = await fake_document_intelligence_adapter.analyze_document(
            document_content=b"Report title\n\nBody paragraph.",
            content_type="text/plain",
            file_id=sample_file_id,
        )
        table = result.tables[0]

        assert table.cells[0].column_span == 2
        assert [c.kind for c in table.cells if c.row_index == 1] == [
            "columnHeader",
            "columnHeader",
        ]

    async def test_fake_spans_resolve_against_its_own_markdown(
        self, fake_document_intelligence_adapter, sample_file_id
    ):
        """The fake's spans have to be internally consistent to be worth testing against."""
        result = await fake_document_intelligence_adapter.analyze_document(
            document_content=b"Report title\n\nBody paragraph.",
            content_type="text/plain",
            file_id=sample_file_id,
        )

        assert_spans_resolve(result.tables[0], result.extracted_text)
        for paragraph in result.paragraphs:
            span = paragraph.spans[0]
            assert (
                result.extracted_text[span.offset : span.offset + span.length]
                == paragraph.content
            )

    async def test_fake_emits_paragraph_roles_and_page_lines(
        self, fake_document_intelligence_adapter, sample_file_id
    ):
        result = await fake_document_intelligence_adapter.analyze_document(
            document_content=b"Report title\n\nBody paragraph.",
            content_type="text/plain",
            file_id=sample_file_id,
        )

        assert result.paragraphs[0].role == "title"
        assert result.pages[0].lines
        assert result.pages[0].unit == "inch"

    async def test_fake_metadata_reports_what_it_emitted(
        self, fake_document_intelligence_adapter, sample_file_id
    ):
        result = await fake_document_intelligence_adapter.analyze_document(
            document_content=b"Report title\n\nBody paragraph.",
            content_type="text/plain",
            file_id=sample_file_id,
        )

        assert result.extraction_metadata.table_count == 1
        assert result.extraction_metadata.paragraph_count == len(result.paragraphs)

    async def test_fake_has_no_raw_analysis_to_offer(
        self, fake_document_intelligence_adapter, sample_file_id
    ):
        """Inventing a service response would make `raw_analysis_stored` lie."""
        result = await fake_document_intelligence_adapter.analyze_document(
            document_content=b"Report title\n\nBody paragraph.",
            content_type="text/plain",
            file_id=sample_file_id,
        )

        assert result.raw_analysis is None
        assert result.extraction_metadata.raw_analysis_stored is False
