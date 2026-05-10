"""ChunkIndex entity for chunk-level tracking."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ChunkIndex(BaseModel):
    """
    ChunkIndex entity representing core chunk positional data in the RAG pipeline.

    Legacy table-entity mapping uses:
    - PartitionKey: {file_id}
    - RowKey: {chunk_id}

    Parent fields (tenant_id, file_version) are derived via file_id FK
    to the files table rather than stored redundantly.
    """

    # Keys (required)
    file_id: str = Field(..., description="Parent file identifier")
    chunk_id: str = Field(..., description="Unique chunk identifier (RowKey)")

    # Chunk positional data
    chunk_index: int = Field(..., ge=0, description="Position in file (0-based)")
    text_preview: str = Field(
        default="",
        description="Text preview (truncated to 100 chars on serialization)",
    )
    start_char: int = Field(default=0, ge=0, description="Start position in source")
    end_char: int = Field(default=0, ge=0, description="End position in source")
    page_number: int | None = Field(default=None, description="Source page (if applicable)")

    # Blob storage references (SSOT for content location)
    chunk_blob_ref: str | None = Field(
        default=None,
        description="Blob storage path for chunk content (e.g., tenant_id/file_id/chunks/chunk_id.json)",
    )
    embedding_blob_ref: str | None = Field(
        default=None,
        description="Blob storage path for embedding vectors (if stored in blob storage)",
    )

    # Chunk-specific metadata persisted to chunk_metadata.metadata_json in SQL
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        description="Chunk-specific metadata (has_table, table_id, section_path, token_count, etc.)",
    )

    # Timestamps
    created_timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Creation time",
    )

    @property
    def partition_key(self) -> str:
        """Generate partition key for legacy table-entity mapping."""
        return self.file_id

    @property
    def row_key(self) -> str:
        """Generate row key for legacy table-entity mapping."""
        return self.chunk_id

    def to_table_entity(self) -> dict[str, Any]:
        """Convert to legacy table-entity format."""
        return {
            "PartitionKey": self.partition_key,
            "RowKey": self.row_key,
            "fileId": self.file_id,
            "chunkIndex": self.chunk_index,
            "textPreview": self.text_preview[:100] if self.text_preview else "",
            "startChar": self.start_char,
            "endChar": self.end_char,
            "pageNumber": self.page_number if self.page_number is not None else -1,
            # Blob storage references
            "chunkBlobRef": self.chunk_blob_ref or "",
            "embeddingBlobRef": self.embedding_blob_ref or "",
            "createdTimestamp": self.created_timestamp.isoformat(),
            # Preserved for backward compatibility with legacy table-entity payloads.
            "embeddingStatus": "pending",
            "vectorDbIds": "{}",
        }

    @classmethod
    def from_table_entity(cls, entity: dict[str, Any]) -> "ChunkIndex":
        """Create ChunkIndex from legacy table-entity format."""
        file_id = entity.get("fileId", "")

        # Legacy support: parse partition key if fileId not present
        if not file_id:
            partition_key = entity.get("PartitionKey", "")
            parts = partition_key.split("|")
            # Old format was {tenant_id}|{file_id}|{file_version}
            file_id = parts[1] if len(parts) > 1 else partition_key

        page_number = entity.get("pageNumber")
        if page_number == -1:
            page_number = None

        return cls(
            file_id=file_id,
            chunk_id=entity["RowKey"],
            chunk_index=entity.get("chunkIndex", 0),
            text_preview=entity.get("textPreview", ""),
            start_char=entity.get("startChar", 0),
            end_char=entity.get("endChar", 0),
            page_number=page_number,
            # Blob storage references
            chunk_blob_ref=entity.get("chunkBlobRef") or None,
            embedding_blob_ref=entity.get("embeddingBlobRef") or None,
            created_timestamp=datetime.fromisoformat(entity["createdTimestamp"])
            if "createdTimestamp" in entity
            else datetime.utcnow(),
        )
