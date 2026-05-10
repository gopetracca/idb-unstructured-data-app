"""Unit tests for ChunkMetadataIndex entity."""

import pytest

from src.core.entities.chunk_metadata_index import ChunkMetadataIndex, EmbeddingStatus


@pytest.mark.unit
class TestChunkMetadataIndex:
    """Tests for chunk metadata state transitions."""

    def test_defaults(self) -> None:
        entity = ChunkMetadataIndex(chunk_id="chunk-001")
        assert entity.embedding_status == EmbeddingStatus.PENDING
        assert entity.metadata_json == {}

    def test_mark_embedded(self) -> None:
        entity = ChunkMetadataIndex(chunk_id="chunk-001")
        entity.mark_embedded()
        assert entity.embedding_status == EmbeddingStatus.COMPLETED

    def test_mark_failed(self) -> None:
        entity = ChunkMetadataIndex(chunk_id="chunk-001")
        entity.mark_failed()
        assert entity.embedding_status == EmbeddingStatus.FAILED
