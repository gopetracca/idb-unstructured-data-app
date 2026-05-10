"""Search result entity for vector database queries."""

from pydantic import BaseModel, Field

from src.core.value_objects.searchable_metadata import SearchableMetadata


class SearchResult(BaseModel):
    """
    Standardized search result format from vector database queries.

    This entity represents a search result returned by any vector database
    (Azure AI Search, PostgreSQL, etc.) after performing similarity search.
    """

    chunk_id: str = Field(..., description="Chunk identifier")
    file_id: str = Field(..., description="Parent file identifier")
    text: str = Field(..., description="Text content of the chunk")
    score: float = Field(..., ge=0.0, description="Similarity/relevance score (cosine or RRF-fused)")
    reranker_score: float | None = Field(
        default=None,
        ge=0.0,
        le=4.0,
        description="Azure semantic reranker score (0-4), present when reranker is enabled",
    )
    metadata: SearchableMetadata = Field(
        default_factory=SearchableMetadata, description="Typed metadata from vector index"
    )

    @property
    def text_preview(self) -> str:
        """Get preview of text content (first 100 chars)."""
        return self.text[:100] if self.text else ""

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"SearchResult(chunk_id={self.chunk_id}, "
            f"file_id={self.file_id}, "
            f"score={self.score:.4f}, "
            f"text='{self.text_preview}...')"
        )

    def __lt__(self, other: "SearchResult") -> bool:
        """Compare by reranker_score when present, else score."""
        self_key = self.reranker_score if self.reranker_score is not None else self.score
        other_key = other.reranker_score if other.reranker_score is not None else other.score
        return self_key < other_key

    def __eq__(self, other: object) -> bool:
        """Check equality based on chunk_id and file_id."""
        if not isinstance(other, SearchResult):
            return False
        return self.chunk_id == other.chunk_id and self.file_id == other.file_id
