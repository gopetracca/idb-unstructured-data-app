"""Unit tests for AzureDocumentIntelligenceAdapter."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config.settings import DocumentIntelligenceSettings
from src.core.errors import DocumentProcessingError, UnsupportedFormatError
from src.infrastructure.azure.adapters.document_intelligence_azure import (
    AzureDocumentIntelligenceAdapter,
)


@pytest.fixture
def mock_document_intelligence_settings() -> DocumentIntelligenceSettings:
    """Create mock Document Intelligence settings."""
    return DocumentIntelligenceSettings(
        endpoint="https://test-di.cognitiveservices.azure.com",
        api_key="test-api-key",
        api_version="2024-11-30",
        use_fake=False,
    )


@pytest.fixture
def mock_analyze_result():
    """Create a mock AnalyzeResult from Azure SDK."""
    # Create mock page
    mock_word1 = MagicMock()
    mock_word1.content = "Hello"
    mock_word1.confidence = 0.95

    mock_word2 = MagicMock()
    mock_word2.content = "World"
    mock_word2.confidence = 0.98

    mock_page = MagicMock()
    mock_page.words = [mock_word1, mock_word2]

    # Create mock result
    mock_result = MagicMock()
    mock_result.content = "# Hello World\n\nThis is extracted content."
    mock_result.pages = [mock_page]
    mock_result.api_version = "2024-11-30"

    return mock_result


@pytest.fixture
def mock_di_client(mock_analyze_result):
    """Create a mock DocumentIntelligenceClient."""
    client = MagicMock()
    client.analyze_document = AsyncMock(return_value=mock_analyze_result)
    client.close = MagicMock()
    return client


@pytest.fixture
def azure_adapter(
    mock_document_intelligence_settings, mock_di_client
) -> AzureDocumentIntelligenceAdapter:
    """Create an AzureDocumentIntelligenceAdapter with mock client."""
    return AzureDocumentIntelligenceAdapter(
        settings=mock_document_intelligence_settings,
        client=mock_di_client,
    )


class TestAzureDocumentIntelligenceAdapter:
    """Tests for AzureDocumentIntelligenceAdapter."""

    def test_get_supported_formats(self, azure_adapter):
        """Test getting supported formats."""
        formats = azure_adapter.get_supported_formats()

        assert isinstance(formats, list)
        assert len(formats) > 0
        assert "application/pdf" in formats
        assert "image/png" in formats
        assert "image/jpeg" in formats

    def test_is_format_supported_pdf(self, azure_adapter):
        """Test PDF format is supported."""
        assert azure_adapter.is_format_supported("application/pdf")

    def test_is_format_supported_images(self, azure_adapter):
        """Test image formats are supported."""
        assert azure_adapter.is_format_supported("image/png")
        assert azure_adapter.is_format_supported("image/jpeg")
        assert azure_adapter.is_format_supported("image/tiff")

    def test_is_format_supported_docx(self, azure_adapter):
        """Test DOCX format is supported."""
        assert azure_adapter.is_format_supported(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    def test_is_format_not_supported(self, azure_adapter):
        """Test unsupported format returns False."""
        assert not azure_adapter.is_format_supported("application/unknown")
        assert not azure_adapter.is_format_supported("video/mp4")
        assert not azure_adapter.is_format_supported("text/plain")  # Not supported in Azure DI

    async def test_analyze_document_success(
        self, azure_adapter, mock_di_client, sample_file_id
    ):
        """Test successful document analysis."""
        content = b"%PDF-1.4 fake pdf content"

        result = await azure_adapter.analyze_document(
            document_content=content,
            content_type="application/pdf",
            file_id=sample_file_id,
            file_version=1,
        )

        assert result.file_id == sample_file_id
        assert result.file_version == 1
        assert result.extracted_text is not None
        assert "Hello World" in result.extracted_text
        assert len(result.pages) >= 1
        assert result.extraction_metadata.extraction_method == "azure-document-intelligence"
        mock_di_client.analyze_document.assert_called_once()

    async def test_analyze_document_extracts_word_count(
        self, azure_adapter, sample_file_id
    ):
        """Test that word count is properly extracted."""
        content = b"%PDF-1.4 fake pdf content"

        result = await azure_adapter.analyze_document(
            document_content=content,
            content_type="application/pdf",
            file_id=sample_file_id,
        )

        # The mock has 2 words: "Hello" and "World"
        assert result.extraction_metadata.word_count == 2
        assert result.pages[0].word_count == 2
        assert result.extracted_text

    async def test_analyze_document_calculates_confidence(
        self, azure_adapter, sample_file_id
    ):
        """Test that confidence is calculated from word confidences."""
        content = b"%PDF-1.4 fake pdf content"

        result = await azure_adapter.analyze_document(
            document_content=content,
            content_type="application/pdf",
            file_id=sample_file_id,
        )

        # Average of 0.95 and 0.98 = 0.965
        assert result.extraction_metadata.extraction_confidence > 0.9
        assert result.extraction_metadata.extraction_confidence < 1.0

    async def test_analyze_document_unsupported_format(
        self, azure_adapter, sample_file_id
    ):
        """Test unsupported format raises error."""
        content = b"some content"

        with pytest.raises(UnsupportedFormatError) as exc_info:
            await azure_adapter.analyze_document(
                document_content=content,
                content_type="application/unknown",
                file_id=sample_file_id,
            )

        assert "application/unknown" in exc_info.value.content_type

    async def test_analyze_document_api_error(
        self, mock_document_intelligence_settings, sample_file_id
    ):
        """Test API error is properly handled."""
        from azure.core.exceptions import HttpResponseError

        mock_error = HttpResponseError(message="API error")
        mock_error.status_code = 400
        mock_error.error = MagicMock()
        mock_error.error.code = "InvalidRequest"

        mock_client = MagicMock()
        mock_client.analyze_document = AsyncMock(side_effect=mock_error)

        adapter = AzureDocumentIntelligenceAdapter(
            settings=mock_document_intelligence_settings,
            client=mock_client,
        )

        with pytest.raises(DocumentProcessingError) as exc_info:
            await adapter.analyze_document(
                document_content=b"content",
                content_type="application/pdf",
                file_id=sample_file_id,
            )

        assert sample_file_id == exc_info.value.file_id
        assert "Azure Document Intelligence failed" in exc_info.value.message

    async def test_analyze_document_with_file_version(
        self, azure_adapter, sample_file_id
    ):
        """Test file version is passed through."""
        content = b"%PDF-1.4 fake pdf content"

        result = await azure_adapter.analyze_document(
            document_content=content,
            content_type="application/pdf",
            file_id=sample_file_id,
            file_version=5,
        )

        assert result.file_version == 5

    async def test_analyze_document_has_created_at(
        self, azure_adapter, sample_file_id
    ):
        """Test created_at timestamp is set."""
        content = b"%PDF-1.4 fake pdf content"

        result = await azure_adapter.analyze_document(
            document_content=content,
            content_type="application/pdf",
            file_id=sample_file_id,
        )

        assert result.created_at is not None
        assert isinstance(result.created_at, datetime)

    def test_close_calls_client_close(self, azure_adapter, mock_di_client):
        """Test that close calls the underlying client close."""
        azure_adapter.close()
        mock_di_client.close.assert_called_once()


class TestAzureDocumentIntelligenceAdapterMappingEdgeCases:
    """Tests for edge cases in result mapping."""

    async def test_empty_pages_with_content(
        self, mock_document_intelligence_settings, sample_file_id
    ):
        """Test handling when pages is empty but content exists."""
        mock_result = MagicMock()
        mock_result.content = "# Title\n\nSome markdown content"
        mock_result.pages = []
        mock_result.api_version = "2024-11-30"

        mock_client = MagicMock()
        mock_client.analyze_document = AsyncMock(return_value=mock_result)

        adapter = AzureDocumentIntelligenceAdapter(
            settings=mock_document_intelligence_settings,
            client=mock_client,
        )

        result = await adapter.analyze_document(
            document_content=b"content",
            content_type="application/pdf",
            file_id=sample_file_id,
        )

        # Should create a single page from content
        assert len(result.pages) == 1
        assert result.extraction_metadata.page_count == 1
        assert result.extraction_metadata.word_count == 5  # "# Title Some markdown content"
        assert result.extracted_text == "# Title\n\nSome markdown content"

    async def test_pages_without_words(
        self, mock_document_intelligence_settings, sample_file_id
    ):
        """Test handling when pages exist but have no words."""
        mock_page = MagicMock()
        mock_page.words = None

        mock_result = MagicMock()
        mock_result.content = "Content"
        mock_result.pages = [mock_page]
        mock_result.api_version = "2024-11-30"

        mock_client = MagicMock()
        mock_client.analyze_document = AsyncMock(return_value=mock_result)

        adapter = AzureDocumentIntelligenceAdapter(
            settings=mock_document_intelligence_settings,
            client=mock_client,
        )

        result = await adapter.analyze_document(
            document_content=b"content",
            content_type="application/pdf",
            file_id=sample_file_id,
        )

        assert len(result.pages) == 1
        assert result.pages[0].word_count == 0

    async def test_no_confidence_in_words(
        self, mock_document_intelligence_settings, sample_file_id
    ):
        """Test handling when words have no confidence scores."""
        mock_word = MagicMock()
        mock_word.content = "Word"
        mock_word.confidence = None

        mock_page = MagicMock()
        mock_page.words = [mock_word]

        mock_result = MagicMock()
        mock_result.content = "Word"
        mock_result.pages = [mock_page]
        mock_result.api_version = "2024-11-30"

        mock_client = MagicMock()
        mock_client.analyze_document = AsyncMock(return_value=mock_result)

        adapter = AzureDocumentIntelligenceAdapter(
            settings=mock_document_intelligence_settings,
            client=mock_client,
        )

        result = await adapter.analyze_document(
            document_content=b"content",
            content_type="application/pdf",
            file_id=sample_file_id,
        )

        # Should default to 0.0 confidence when not available
        assert result.extraction_metadata.extraction_confidence == 0.0
