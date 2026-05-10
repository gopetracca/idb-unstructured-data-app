"""Embedding entity representing a vector embedding for a chunk."""

from datetime import datetime

from pydantic import BaseModel, Field


class EmbeddingMetadata(BaseModel):
    """Metadata associated with an embedding."""

    model_version: str = Field(default="", description="Embedding model version")
    token_count: int = Field(default=0, ge=0, description="Token count of source text")
    chunking_strategy: str = Field(default="", description="Strategy used for chunking")
    chunk_size: int = Field(default=0, ge=0, description="Original chunk size")
    overlap_chars: int = Field(default=0, ge=0, description="Overlap between chunks")
    page_number: int | None = Field(default=None, description="Physical page number (1-indexed) of the chunk's starting position")
    section_path: list[str] | None = Field(default=None, description="Heading hierarchy path for the chunk")
    has_table: bool = Field(default=False, description="Whether chunk contains an HTML table")
    table_id: str | None = Field(default=None, description="Table identifier if chunk is a table")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")

class Embedding(BaseModel):
    """
    Represents a vector embedding for a document chunk.

    Contains the vector representation along with source chunk info
    and metadata needed for vector database ingestion.
    """

    file_id: str = Field(..., description="Parent file identifier")
    chunk_id: str = Field(..., description="Source chunk identifier")
    embedding_model: str = Field(..., description="Model used for embedding")
    embedding_dimension: int = Field(..., ge=1, description="Vector dimension")
    vector: list[float] = Field(..., description="Embedding vector")
    chunk_text: str = Field(..., description="Original chunk text")
    metadata: EmbeddingMetadata = Field(
        default_factory=EmbeddingMetadata, description="Embedding metadata"
    )

    @property
    def vector_preview(self) -> list[float]:
        """Get first 5 elements of vector for preview."""
        return self.vector[:5] if self.vector else []

    @property
    def chunk_text_preview(self) -> str:
        """Get preview of chunk text (first 100 chars)."""
        return self.chunk_text[:100] if self.chunk_text else ""
