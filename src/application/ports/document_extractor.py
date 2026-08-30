"""Port interface for the document extraction service."""

from abc import ABC, abstractmethod

from src.core.entities.document_analysis import MarkdownOutput


class DocumentExtractorPort(ABC):
    """
    Abstract interface for turning a document into text and structure.

    This port defines the contract that any extraction implementation must fulfil —
    Azure Document Intelligence, a fake for local development, or another service — so
    that no application or domain code knows which is in play.

    **The offset invariant.** Every block in :attr:`MarkdownOutput.blocks` carries a
    ``(start, end)`` range that indexes into the ``extracted_text`` returned alongside it
    and yields that block's text. Holding to that is the *adapter's* job, not the
    provider's: an adapter whose service reports offsets into the text it returns (as
    Document Intelligence does) passes them through, and one whose service reports no
    such thing renders the text itself and records the range as it emits each element.
    A consumer may rely on the invariant without knowing which happened.

    The same division applies to a table's ``rendered``, ``render_prefix``, ``rows`` and
    ``render_suffix``: the adapter partitions the rendering it produced, and no consumer
    parses markup to recover a table or part of one.
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
        Analyze a document and extract its text and structure.

        Args:
            document_content: Raw document bytes
            content_type: MIME type of the document
            file_id: Unique identifier for the file
            file_version: Version number of the file

        Returns:
            MarkdownOutput containing the extracted text, the canonical block list, the
            document's structural elements, and extraction metadata

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


# The port was named after the one service that implemented it. The old name stays
# importable so a caller — or a change in flight against it — does not break on the
# rename; it is the same class, not a subclass.
DocumentIntelligencePort = DocumentExtractorPort

__all__ = ["DocumentExtractorPort", "DocumentIntelligencePort"]
