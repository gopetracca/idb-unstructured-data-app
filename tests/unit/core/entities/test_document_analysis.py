"""Unit tests for document analysis entities."""

from datetime import datetime

import pytest

from src.core.entities.document_analysis import (
    DocumentMetadata,
    ExtractionMetadata,
    MarkdownOutput,
    PageContent,
)


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
