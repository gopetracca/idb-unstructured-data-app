"""Unit tests for ChunkIndex entity."""

import pytest

from src.core.entities.chunk_index import ChunkIndex
from src.core.entities.chunk_metadata_index import EmbeddingStatus


@pytest.mark.unit
class TestChunkIndex:
    """Tests for ChunkIndex entity."""

    def test_create_chunk_index_minimal(self) -> None:
        """Test creating ChunkIndex with minimal required fields."""
        chunk = ChunkIndex(
            file_id="file-001",
            chunk_id="chunk-001",
            chunk_index=0,
        )

        assert chunk.file_id == "file-001"
        assert chunk.chunk_id == "chunk-001"
        assert chunk.chunk_index == 0

    def test_create_chunk_index_full(self, sample_chunk_index: ChunkIndex) -> None:
        """Test creating ChunkIndex with all fields."""
        assert sample_chunk_index.text_preview != ""
        assert sample_chunk_index.start_char == 0
        assert sample_chunk_index.end_char == 500
        assert sample_chunk_index.page_number == 1

    def test_partition_key_format(self, sample_chunk_index: ChunkIndex) -> None:
        """Test partition key is formatted correctly."""
        assert sample_chunk_index.partition_key == sample_chunk_index.file_id

    def test_row_key_is_chunk_id(self, sample_chunk_index: ChunkIndex) -> None:
        """Test row key equals chunk_id."""
        assert sample_chunk_index.row_key == sample_chunk_index.chunk_id

    def test_to_table_entity(self, sample_chunk_index: ChunkIndex) -> None:
        """Test conversion to legacy table-entity format."""
        entity = sample_chunk_index.to_table_entity()

        assert entity["PartitionKey"] == sample_chunk_index.partition_key
        assert entity["RowKey"] == sample_chunk_index.chunk_id
        assert entity["fileId"] == sample_chunk_index.file_id
        assert entity["chunkIndex"] == sample_chunk_index.chunk_index
        assert entity["textPreview"] == sample_chunk_index.text_preview[:100]
        assert entity["embeddingStatus"] == "pending"

    def test_from_table_entity(self, sample_chunk_index: ChunkIndex) -> None:
        """Test creation from legacy table-entity payload."""
        entity = sample_chunk_index.to_table_entity()
        restored = ChunkIndex.from_table_entity(entity)

        assert restored.file_id == sample_chunk_index.file_id
        assert restored.chunk_id == sample_chunk_index.chunk_id
        assert restored.chunk_index == sample_chunk_index.chunk_index

    def test_text_preview_truncation(self) -> None:
        """Test that text preview is truncated to 100 characters."""
        long_text = "x" * 200
        chunk = ChunkIndex(
            file_id="f",
            chunk_id="c",
            chunk_index=0,
            text_preview=long_text,
        )
        entity = chunk.to_table_entity()

        assert len(entity["textPreview"]) == 100

    def test_page_number_none_handling(self) -> None:
        """Test handling of None page number."""
        chunk = ChunkIndex(
            file_id="f",
            chunk_id="c",
            chunk_index=0,
            page_number=None,
        )
        entity = chunk.to_table_entity()

        assert entity["pageNumber"] == -1

        restored = ChunkIndex.from_table_entity(entity)
        assert restored.page_number is None


@pytest.mark.unit
class TestEmbeddingStatus:
    """Tests for EmbeddingStatus enum."""

    def test_all_statuses_defined(self) -> None:
        """Test all expected statuses are defined."""
        expected = ["pending", "completed", "failed"]
        actual = [s.value for s in EmbeddingStatus]

        for status in expected:
            assert status in actual
