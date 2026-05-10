"""Unit tests for Chunk entity."""

from datetime import datetime

import pytest

from src.core.entities.chunk import Chunk, ChunkMetadata


class TestChunkMetadata:
    """Tests for ChunkMetadata."""

    def test_create_default_metadata(self):
        """Test creating metadata with default values."""
        metadata = ChunkMetadata()

        assert metadata.overlap_chars == 50
        assert metadata.token_count is None
        assert metadata.page_label is None
        assert isinstance(metadata.created_at, datetime)

    def test_create_custom_metadata(self):
        """Test creating metadata with custom values."""
        metadata = ChunkMetadata(
            overlap_chars=100,
            token_count=256,
            page_label="iv",
        )

        assert metadata.overlap_chars == 100
        assert metadata.token_count == 256
        assert metadata.page_label == "iv"

    def test_model_dump(self):
        """Test converting metadata to dictionary via model_dump."""
        metadata = ChunkMetadata(
            overlap_chars=50,
            token_count=128,
            page_label="1",
        )

        result = metadata.model_dump(mode="json")

        assert result["overlap_chars"] == 50
        assert result["token_count"] == 128
        assert result["page_label"] == "1"
        assert "created_at" in result

    def test_model_validate(self):
        """Test creating metadata from dictionary via model_validate."""
        data = {
            "overlap_chars": 100,
            "token_count": 256,
            "page_label": "xii",
            "created_at": "2026-01-28T10:00:00",
        }

        metadata = ChunkMetadata.model_validate(data)

        assert metadata.overlap_chars == 100
        assert metadata.token_count == 256
        assert metadata.page_label == "xii"

    def test_model_validate_with_defaults(self):
        """Test creating metadata from empty dictionary uses defaults."""
        metadata = ChunkMetadata.model_validate({})

        assert metadata.overlap_chars == 50
        assert metadata.token_count is None

    def test_chunking_strategy_and_chunk_size_default_none(self):
        """New fields default to None and are not silently dropped."""
        metadata = ChunkMetadata()

        assert metadata.chunking_strategy is None
        assert metadata.chunk_size is None

    def test_chunking_strategy_and_chunk_size_roundtrip(self):
        """chunking_strategy and chunk_size survive model_dump/model_validate."""
        metadata = ChunkMetadata(
            chunking_strategy="fixed_size",
            chunk_size=512,
        )

        dumped = metadata.model_dump(mode="json")
        assert dumped["chunking_strategy"] == "fixed_size"
        assert dumped["chunk_size"] == 512

        restored = ChunkMetadata.model_validate(dumped)
        assert restored.chunking_strategy == "fixed_size"
        assert restored.chunk_size == 512

    def test_table_chunk_metadata(self):
        """Table-chunk metadata fields survive round-trip."""
        metadata = ChunkMetadata(
            has_table=True,
            table_id="table_0",
            chunking_strategy="markdown_aware",
            chunk_size=256,
            token_count=80,
            section_path=["Introduction", "Background"],
            page_label="iv",
        )

        dumped = metadata.model_dump(mode="json")
        assert dumped["has_table"] is True
        assert dumped["table_id"] == "table_0"
        assert dumped["chunking_strategy"] == "markdown_aware"
        assert dumped["chunk_size"] == 256


class TestChunk:
    """Tests for Chunk entity."""

    def test_create_chunk(self):
        """Test creating a chunk entity."""
        chunk = Chunk(
            file_id="file-123",
            chunk_id="file-123_chunk_0",
            chunk_index=0,
            text="This is sample text content.",
            start_char=0,
            end_char=28,
            page_number=1,
        )

        assert chunk.file_id == "file-123"
        assert chunk.chunk_id == "file-123_chunk_0"
        assert chunk.chunk_index == 0
        assert chunk.text == "This is sample text content."
        assert chunk.start_char == 0
        assert chunk.end_char == 28
        assert chunk.page_number == 1

    def test_char_count_property(self):
        """Test char_count property."""
        chunk = Chunk(
            file_id="file-123",
            chunk_id="file-123_chunk_0",
            chunk_index=0,
            text="Hello World",
            start_char=0,
            end_char=11,
        )

        assert chunk.char_count == 11

    def test_text_preview_property(self):
        """Test text_preview property with short text."""
        chunk = Chunk(
            file_id="file-123",
            chunk_id="file-123_chunk_0",
            chunk_index=0,
            text="Short text",
            start_char=0,
            end_char=10,
        )

        assert chunk.text_preview == "Short text"

    def test_text_preview_property_long_text(self):
        """Test text_preview property truncates long text."""
        long_text = "A" * 200
        chunk = Chunk(
            file_id="file-123",
            chunk_id="file-123_chunk_0",
            chunk_index=0,
            text=long_text,
            start_char=0,
            end_char=200,
        )

        assert len(chunk.text_preview) == 100
        assert chunk.text_preview == "A" * 100

    def test_model_dump(self):
        """Test converting chunk to dictionary via model_dump."""
        chunk = Chunk(
            file_id="file-123",
            chunk_id="file-123_chunk_0",
            chunk_index=0,
            text="Sample text",
            start_char=0,
            end_char=11,
            page_number=1,
            metadata=ChunkMetadata(overlap_chars=50),
        )

        result = chunk.model_dump(mode="json")

        assert result["file_id"] == "file-123"
        assert result["chunk_id"] == "file-123_chunk_0"
        assert result["chunk_index"] == 0
        assert result["text"] == "Sample text"
        assert result["start_char"] == 0
        assert result["end_char"] == 11
        assert result["page_number"] == 1
        assert "metadata" in result

    def test_model_validate(self):
        """Test creating chunk from dictionary via model_validate."""
        data = {
            "file_id": "file-456",
            "chunk_id": "file-456_chunk_1",
            "chunk_index": 1,
            "text": "More content",
            "start_char": 100,
            "end_char": 112,
            "page_number": 2,
            "metadata": {
                "overlap_chars": 42,
            },
        }

        chunk = Chunk.model_validate(data)

        assert chunk.file_id == "file-456"
        assert chunk.chunk_id == "file-456_chunk_1"
        assert chunk.chunk_index == 1
        assert chunk.text == "More content"
        assert chunk.metadata.overlap_chars == 42

    def test_model_dump_roundtrip(self):
        """Test chunk roundtrip via model_dump/model_validate."""
        chunk = Chunk(
            file_id="file-123",
            chunk_id="file-123_chunk_0",
            chunk_index=0,
            text="Storage test",
            start_char=0,
            end_char=12,
        )

        result = chunk.model_dump(mode="json")

        assert result["file_id"] == "file-123"
        assert result["text"] == "Storage test"

    def test_model_validate_from_json_dict(self):
        """Test creating chunk from JSON-like dictionary."""
        data = {
            "file_id": "file-789",
            "chunk_id": "file-789_chunk_0",
            "chunk_index": 0,
            "text": "Loaded from storage",
            "start_char": 0,
            "end_char": 19,
        }

        chunk = Chunk.model_validate(data)

        assert chunk.file_id == "file-789"
        assert chunk.text == "Loaded from storage"

    def test_chunk_without_page_number(self):
        """Test creating chunk without page number."""
        chunk = Chunk(
            file_id="file-123",
            chunk_id="file-123_chunk_0",
            chunk_index=0,
            text="No page",
            start_char=0,
            end_char=7,
        )

        assert chunk.page_number is None
