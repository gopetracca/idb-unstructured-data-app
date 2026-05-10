"""Chunk entity representing a processed text chunk."""

from datetime import datetime

from pydantic import BaseModel, Field


class ChunkMetadata(BaseModel):
    """Metadata associated with a chunk."""

    overlap_chars: int = Field(default=50, description="Overlap between chunks")
    token_count: int | None = Field(default=None, description="Token count (if calculated)")
    section_path: list[str] | None = Field(
        default=None, description="Heading hierarchy path (e.g. ['Introduction', 'Background'])"
    )
    has_table: bool = Field(default=False, description="Whether chunk contains an HTML table")
    table_id: str | None = Field(default=None, description="Table identifier if chunk is a table")
    page_label: str | None = Field(
        default=None,
        description="Source page label as printed in the document (e.g. iv, 1)",
    )
    chunking_strategy: str | None = Field(default=None, description="Strategy used to produce this chunk")
    chunk_size: int | None = Field(default=None, description="Configured chunk size for the strategy")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")

class Chunk(BaseModel):
    """
    Represents a text chunk from document processing.

    A chunk is a segment of text extracted from a document,
    ready for vectorization and storage.
    """

    file_id: str = Field(..., description="Parent file identifier")
    chunk_id: str = Field(..., description="Unique chunk identifier")
    chunk_index: int = Field(..., ge=0, description="Position in file (0-based)")
    text: str = Field(..., description="Chunk text content")
    start_char: int = Field(default=0, ge=0, description="Start position in source text")
    end_char: int = Field(default=0, ge=0, description="End position in source text")
    page_number: int | None = Field(default=None, description="Source page number (if applicable)")
    metadata: ChunkMetadata = Field(default_factory=ChunkMetadata, description="Chunk metadata")

    @property
    def char_count(self) -> int:
        """Get character count of chunk text."""
        return len(self.text)

    @property
    def text_preview(self) -> str:
        """Get preview of chunk text (first 100 chars)."""
        return self.text[:100] if self.text else ""
