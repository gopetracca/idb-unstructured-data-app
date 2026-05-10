"""Port interface for Document Intelligence service."""

from abc import ABC, abstractmethod

from src.core.entities.document_analysis import MarkdownOutput


class DocumentIntelligencePort(ABC):
    """
    Abstract interface for document intelligence operations.

    This port defines the contract that any document intelligence
    implementation must fulfill, allowing for both fake (development)
    and real (Azure) implementations.
    """

    @abstractmethod
    async def analyze_document(
        self,
        document_content: bytes,
        content_type: str,
        file_id: str,
        file_version: int = 1,
    ) -> MarkdownOutput:
        """
        Analyze a document and extract text as markdown.

        Args:
            document_content: Raw document bytes
            content_type: MIME type of the document
            file_id: Unique identifier for the file
            file_version: Version number of the file

        Returns:
            MarkdownOutput containing extracted text and metadata

        Raises:
            UnsupportedFormatError: If content_type is not supported
            DocumentProcessingError: If extraction fails
        """
        pass

    @abstractmethod
    def get_supported_formats(self) -> list[str]:
        """
        Get list of supported document MIME types.

        Returns:
            List of MIME type strings that can be processed
        """
        pass

    def is_format_supported(self, content_type: str) -> bool:
        """
        Check if a content type is supported.

        Args:
            content_type: MIME type to check

        Returns:
            True if format is supported, False otherwise
        """
        return content_type.lower() in [f.lower() for f in self.get_supported_formats()]
