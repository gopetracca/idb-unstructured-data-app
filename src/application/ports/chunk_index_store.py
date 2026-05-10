"""Chunk index storage port for chunk lifecycle operations."""

from typing import Any, Protocol

from src.core.entities.chunk_index import ChunkIndex
from src.core.entities.chunk_metadata_index import EmbeddingStatus


class ChunkIndexStorePort(Protocol):
    """Port interface for chunk index storage operations."""

    async def close(self) -> None:
        """Close any owned client/session resources."""
        ...

    async def create(self, chunk_index: ChunkIndex) -> ChunkIndex:
        """Create a chunk index record."""
        ...

    async def get_by_id(self, chunk_id: str) -> ChunkIndex | None:
        """Get a chunk by ID."""
        ...

    async def update(self, chunk_index: ChunkIndex) -> ChunkIndex:
        """Update a chunk index record."""
        ...

    async def upsert(self, chunk_index: ChunkIndex) -> ChunkIndex:
        """Create or update a chunk index record."""
        ...

    async def delete(self, chunk_id: str) -> bool:
        """Delete a chunk record by ID."""
        ...

    async def batch_create(self, chunks: list[ChunkIndex]) -> list[ChunkIndex]:
        """Batch-create chunk index records."""
        ...

    async def query_by_file(
        self,
        file_id: str,
        limit: int | None = None,
    ) -> list[ChunkIndex]:
        """Query chunks by parent file ID."""
        ...

    async def query_by_file_page(
        self,
        file_id: str,
        offset: int,
        limit: int,
    ) -> list[ChunkIndex]:
        """Query a chunk page by parent file ID."""
        ...

    async def query_by_embedding_status(
        self,
        file_id: str,
        status: EmbeddingStatus,
        limit: int | None = None,
    ) -> list[ChunkIndex]:
        """Query chunks by embedding status."""
        ...

    async def query_pending_embeddings(
        self,
        file_id: str,
        limit: int | None = None,
    ) -> list[ChunkIndex]:
        """Query chunks pending embedding."""
        ...

    async def delete_by_file(self, file_id: str) -> int:
        """Delete all chunks for a file."""
        ...

    async def count_by_file(self, file_id: str) -> int:
        """Count chunks for a file."""
        ...

    async def count_embedded(self, file_id: str) -> int:
        """Count embedded chunks for a file."""
        ...

    async def mark_embedded(
        self,
        chunk_id: str,
        vector_db_id: str,
        db_name: str = "azure-ai-search",
    ) -> ChunkIndex | None:
        """Mark chunk as embedded and persist vector reference."""
        ...

    async def mark_failed(self, chunk_id: str) -> ChunkIndex | None:
        """Mark chunk embedding as failed."""
        ...

    async def update_blob_references(
        self,
        chunk_id: str,
        chunk_blob_ref: str | None = None,
        embedding_blob_ref: str | None = None,
    ) -> ChunkIndex | None:
        """
        Update blob storage references for a chunk.

        Args:
            chunk_id: Chunk identifier
            chunk_blob_ref: Optional chunk content blob path to update
            embedding_blob_ref: Optional embedding blob path to update

        Returns:
            Updated ChunkIndex or None if not found
        """
        ...

    async def batch_get_metadata(
        self,
        chunk_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Return {chunk_id: metadata_json} for the given chunk IDs."""
        ...

    async def get_chunk_ids_for_db(
        self,
        file_id: str,
        db_name: str = "azure-ai-search",
    ) -> list[str]:
        """Get persisted vector IDs for a file in a given DB."""
        ...
