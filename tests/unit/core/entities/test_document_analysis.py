"""Unit tests for document analysis entities."""


import pytest

from src.core.entities.document_analysis import (
    BoundingRegion,
    DocumentLine,
    DocumentMetadata,
    ExtractedFigure,
    ExtractedParagraph,
    ExtractedTable,
    ExtractionMetadata,
    KeyValueElement,
    KeyValuePair,
    MarkdownOutput,
    PageContent,
    TableCell,
    TextSpan,
)
from tests.support.table_reconstruction import assert_cells_tile_grid

pytestmark = pytest.mark.unit


class TestPageContent:
    """Tests for PageContent value object."""

    def test_create_page_content(self):
        """Test creating a PageContent instance."""
        page = PageContent(
            page_number=1,
            text="Sample text content",
            word_count=3,
        )

        assert page.page_number == 1
        assert page.text == "Sample text content"
        assert page.word_count == 3

    def test_page_content_defaults(self):
        """Test PageContent default values."""
        page = PageContent(page_number=1)

        assert page.text == ""
        assert page.word_count == 0

    def test_page_number_validation(self):
        """Test page_number must be >= 1."""
        with pytest.raises(ValueError):
            PageContent(page_number=0)


class TestExtractionMetadata:
    """Tests for ExtractionMetadata value object."""

    def test_create_extraction_metadata(self):
        """Test creating an ExtractionMetadata instance."""
        metadata = ExtractionMetadata(
            page_count=10,
            word_count=5000,
            extraction_confidence=0.95,
            extraction_method="azure-document-intelligence",
            api_version="2024-11-30",
        )

        assert metadata.page_count == 10
        assert metadata.word_count == 5000
        assert metadata.extraction_confidence == 0.95
        assert metadata.extraction_method == "azure-document-intelligence"
        assert metadata.api_version == "2024-11-30"

    def test_extraction_metadata_defaults(self):
        """Test ExtractionMetadata default values."""
        metadata = ExtractionMetadata()

        assert metadata.page_count == 0
        assert metadata.word_count == 0
        assert metadata.extraction_confidence == 0.0
        assert metadata.extraction_method == "azure-document-intelligence"
        assert metadata.api_version == "2024-11-30"

    def test_confidence_range_validation(self):
        """Test extraction_confidence must be between 0 and 1."""
        with pytest.raises(ValueError):
            ExtractionMetadata(extraction_confidence=1.5)

        with pytest.raises(ValueError):
            ExtractionMetadata(extraction_confidence=-0.1)


class TestMarkdownOutput:
    """Tests for MarkdownOutput value object."""

    def test_create_markdown_output(self, sample_file_id: str):
        """Test creating a MarkdownOutput instance."""
        output = MarkdownOutput(
            file_id=sample_file_id,
            file_version=1,
            extracted_text="Sample text",
            pages=[PageContent(page_number=1, text="Sample text", word_count=2)],
            extraction_metadata=ExtractionMetadata(page_count=1, word_count=2),
        )

        assert output.file_id == sample_file_id
        assert output.file_version == 1
        assert output.extracted_text == "Sample text"
        assert len(output.pages) == 1
        assert output.extraction_metadata.page_count == 1

    def test_markdown_output_model_dump(self, sample_markdown_output: MarkdownOutput):
        """Test MarkdownOutput serialization via model_dump."""
        result = sample_markdown_output.model_dump(mode="json")

        assert result["file_id"] == sample_markdown_output.file_id
        assert result["file_version"] == 1
        assert "extracted_text" in result
        assert "pages" in result
        assert len(result["pages"]) == 1
        assert result["pages"][0]["page_number"] == 1
        assert "extraction_metadata" in result
        assert result["extraction_metadata"]["page_count"] == 1
        assert "created_at" in result

    def test_markdown_output_model_validate(self, sample_markdown_output: MarkdownOutput):
        """Test MarkdownOutput deserialization via model_validate."""
        data = sample_markdown_output.model_dump(mode="json")
        restored = MarkdownOutput.model_validate(data)

        assert restored.file_id == sample_markdown_output.file_id
        assert restored.file_version == sample_markdown_output.file_version
        assert restored.extracted_text == sample_markdown_output.extracted_text
        assert len(restored.pages) == len(sample_markdown_output.pages)
        assert (
            restored.extraction_metadata.page_count
            == sample_markdown_output.extraction_metadata.page_count
        )

    def test_markdown_output_roundtrip(self, sample_file_id: str):
        """Test MarkdownOutput serialization roundtrip."""
        original = MarkdownOutput(
            file_id=sample_file_id,
            file_version=2,
            extracted_text="Test content for roundtrip",
            pages=[
                PageContent(page_number=1, text="Page 1 content", word_count=3),
                PageContent(page_number=2, text="Page 2 content", word_count=3),
            ],
            extraction_metadata=ExtractionMetadata(
                page_count=2,
                word_count=6,
                extraction_confidence=0.99,
                extraction_method="test-method",
                api_version="test-version",
            ),
        )

        data = original.model_dump(mode="json")
        restored = MarkdownOutput.model_validate(data)

        assert restored.file_id == original.file_id
        assert restored.file_version == original.file_version
        assert len(restored.pages) == 2
        assert restored.extraction_metadata.extraction_method == "test-method"


class TestDocumentMetadata:
    """Tests for DocumentMetadata entity."""

    def test_create_document_metadata(self, sample_file_id: str):
        """Test creating a DocumentMetadata instance."""
        metadata = DocumentMetadata(
            file_id=sample_file_id,
            file_version=1,
            blob_name="document.pdf",
            content_type="application/pdf",
            size_bytes=1024000,
            source_container="raw",
            source_path="file-123/original/document.pdf",
        )

        assert metadata.file_id == sample_file_id
        assert metadata.blob_name == "document.pdf"
        assert metadata.content_type == "application/pdf"
        assert metadata.size_bytes == 1024000

    def test_document_metadata_defaults(self, sample_file_id: str):
        """Test DocumentMetadata default values."""
        metadata = DocumentMetadata(
            file_id=sample_file_id,
            blob_name="test.txt",
        )

        assert metadata.file_version == 1
        assert metadata.content_type == "application/octet-stream"
        assert metadata.size_bytes == 0
        assert metadata.source_container == "raw"
        assert metadata.source_path == ""


def _table() -> ExtractedTable:
    """A 3x2 table with a merged title cell over a header row over a data row."""
    return ExtractedTable(
        row_count=3,
        column_count=2,
        cells=[
            TableCell(
                row_index=0,
                column_index=0,
                column_span=2,
                kind="columnHeader",
                content="Budget Summary",
                spans=[TextSpan(offset=2, length=14)],
                bounding_regions=[BoundingRegion(page_number=1, polygon=[0.0] * 8)],
            ),
            TableCell(row_index=1, column_index=0, kind="columnHeader", content="Year"),
            TableCell(row_index=1, column_index=1, kind="columnHeader", content="Amount"),
            TableCell(row_index=2, column_index=0, content="2026"),
            TableCell(row_index=2, column_index=1, content="1,250"),
        ],
        caption="Table 1",
        footnotes=["Amounts in thousands."],
        bounding_regions=[
            BoundingRegion(page_number=1, polygon=[]),
            BoundingRegion(page_number=2, polygon=[]),
            BoundingRegion(page_number=1, polygon=[]),
        ],
    )


class TestExtractedTable:
    """A table has to be rebuildable from its cells alone."""

    def test_to_grid_expands_merged_cells(self):
        assert _table().to_grid() == [
            ["Budget Summary", "Budget Summary"],
            ["Year", "Amount"],
            ["2026", "1,250"],
        ]

    def test_cells_tile_the_declared_grid(self):
        assert_cells_tile_grid(_table())

    def test_missing_cells_leave_holes_rather_than_shifting_the_grid(self):
        """A dropped cell must not silently renumber its neighbours."""
        table = ExtractedTable(
            row_count=2,
            column_count=2,
            cells=[
                TableCell(row_index=0, column_index=0, content="a"),
                TableCell(row_index=1, column_index=1, content="d"),
            ],
        )

        assert table.to_grid() == [["a", None], [None, "d"]]

    def test_page_numbers_are_ordered_and_deduplicated(self):
        assert _table().page_numbers == [1, 2]

    def test_empty_table_has_an_empty_grid(self):
        assert ExtractedTable().to_grid() == []

    def test_cell_defaults_match_the_service_omitting_spans_of_one(self):
        cell = TableCell()

        assert cell.row_span == 1
        assert cell.column_span == 1
        assert cell.kind == "content"


class TestStructuralValueObjects:
    """The new value objects round-trip through JSON."""

    def test_markdown_output_carries_structure(self, sample_file_id: str):
        output = MarkdownOutput(
            file_id=sample_file_id,
            extracted_text="| Budget Summary ||",
            tables=[_table()],
            paragraphs=[ExtractedParagraph(content="Budget Summary", role="title")],
            figures=[ExtractedFigure(figure_id="1.1", caption="Figure 1")],
            key_value_pairs=[
                KeyValuePair(key=KeyValueElement(content="k"), value=KeyValueElement(content="v"))
            ],
            content_format="markdown",
            model_id="prebuilt-layout",
        )

        restored = MarkdownOutput.model_validate(output.model_dump(mode="json"))

        assert restored.tables[0].to_grid() == output.tables[0].to_grid()
        assert restored.paragraphs[0].role == "title"
        assert restored.figures[0].caption == "Figure 1"
        assert restored.key_value_pairs[0].value.content == "v"
        assert restored.content_format == "markdown"

    def test_page_content_carries_geometry_and_lines(self):
        page = PageContent(
            page_number=2,
            text="a b",
            word_count=2,
            width=8.5,
            height=11.0,
            unit="inch",
            angle=0.0,
            lines=[DocumentLine(content="a b", spans=[TextSpan(offset=0, length=3)])],
        )

        restored = PageContent.model_validate(page.model_dump(mode="json"))

        assert restored.unit == "inch"
        assert restored.lines[0].spans[0].length == 3

    def test_raw_analysis_is_excluded_from_serialisation(self, sample_file_id: str):
        """text.json must not carry a second copy of the raw payload."""
        output = MarkdownOutput(file_id=sample_file_id, raw_analysis={"modelId": "x"})

        dumped = output.model_dump(mode="json")

        assert "raw_analysis" not in dumped
        assert output.raw_analysis == {"modelId": "x"}


class TestBackwardCompatibility:
    """Output written before structural preservation existed must still load."""

    PRE_CHANGE_TEXT_JSON = {
        "file_id": "file-123",
        "file_version": 1,
        "extracted_text": "# Title\n\nBody text.",
        "pages": [{"page_number": 1, "text": "Title Body text.", "word_count": 3}],
        "extraction_metadata": {
            "page_count": 1,
            "word_count": 3,
            "extraction_confidence": 0.97,
            "extraction_method": "azure-document-intelligence",
            "api_version": "2024-11-30",
        },
        "created_at": "2026-01-01T00:00:00",
    }

    def test_pre_change_output_deserialises(self):
        output = MarkdownOutput.model_validate(self.PRE_CHANGE_TEXT_JSON)

        assert output.extracted_text == "# Title\n\nBody text."
        assert output.pages[0].word_count == 3
        assert output.extraction_metadata.extraction_confidence == 0.97

    def test_structural_fields_default_to_empty(self):
        output = MarkdownOutput.model_validate(self.PRE_CHANGE_TEXT_JSON)

        assert output.tables == []
        assert output.figures == []
        assert output.paragraphs == []
        assert output.sections == []
        assert output.styles == []
        assert output.key_value_pairs == []
        assert output.content_format is None
        assert output.raw_analysis is None

    def test_pre_change_metadata_reports_nothing_preserved(self):
        """This is how a document extracted before the change is told apart."""
        output = MarkdownOutput.model_validate(self.PRE_CHANGE_TEXT_JSON)

        assert output.extraction_metadata.table_count == 0
        assert output.extraction_metadata.raw_analysis_stored is False

    def test_existing_fields_keep_their_meaning(self):
        """The additive fields must not have moved anything."""
        output = MarkdownOutput.model_validate(self.PRE_CHANGE_TEXT_JSON)
        dumped = output.model_dump(mode="json")

        for key, value in self.PRE_CHANGE_TEXT_JSON.items():
            if key in ("pages", "extraction_metadata", "created_at"):
                continue
            assert dumped[key] == value
        assert dumped["pages"][0]["text"] == "Title Body text."
        assert dumped["extraction_metadata"]["word_count"] == 3
