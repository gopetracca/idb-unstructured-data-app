"""Vector document entity for vector database operations."""

from pydantic import BaseModel, Field, field_validator

from src.core.value_objects.searchable_metadata import SearchableMetadata


class VectorDocument(BaseModel):
    """
    Standardized document format for vector database ingestion.

    This entity represents a document chunk with its embedding vector
    that can be indexed in any vector database (Azure AI Search, PostgreSQL, etc.).

    The id field uses a composite key pattern to ensure uniqueness across files.
    """

    id: str = Field(..., description="Unique document identifier (composite: file_id_chunk_id)")
    chunk_id: str = Field(..., description="Chunk identifier within the file")
    file_id: str = Field(..., description="Parent file identifier")
    text: str = Field(..., description="Text content of the chunk")
    vector: list[float] = Field(..., description="Embedding vector")
    metadata: SearchableMetadata = Field(
        default_factory=SearchableMetadata, description="Typed metadata for indexing"
    )

    @field_validator("vector")
    @classmethod
    def validate_vector_not_empty(cls, v: list[float]) -> list[float]:
        """Validate that vector is not empty."""
        if not v:
            raise ValueError("Vector cannot be empty")
        return v

    @field_validator("id")
    @classmethod
    def validate_id_format(cls, v: str) -> str:
        """Validate that id follows the composite key pattern."""
        if "_" not in v:
            raise ValueError("ID must follow pattern: file_id_chunk_id")
        return v

    @property
    def vector_dimension(self) -> int:
        """Get the dimension of the embedding vector."""
        return len(self.vector)

    @property
    def vector_preview(self) -> list[float]:
        """Get preview of vector (first 5 elements)."""
        return self.vector[:5] if self.vector else []

    @property
    def text_preview(self) -> str:
        """Get preview of text content (first 100 chars)."""
        return self.text[:100] if self.text else ""

    @classmethod
    def create_id(cls, file_id: str, chunk_id: str) -> str:
        """
        Create composite ID from file_id and chunk_id.

        Args:
            file_id: File identifier
            chunk_id: Chunk identifier

        Returns:
            Composite ID in format: file_id_chunk_id
        """
        return f"{file_id}_{chunk_id}"

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"VectorDocument(id={self.id}, "
            f"dim={self.vector_dimension}, "
            f"text='{self.text_preview}...')"
        )
