"""Unit tests for Embedding entity."""

from datetime import datetime

import pytest

from src.core.entities.embedding import Embedding, EmbeddingMetadata


class TestEmbeddingMetadata:
    """Tests for EmbeddingMetadata."""

    def test_create_default_metadata(self):
        """Test creating metadata with default values."""
        metadata = EmbeddingMetadata()

        assert metadata.model_version == ""
        assert metadata.token_count == 0
        assert metadata.chunking_strategy == ""
        assert metadata.chunk_size == 0
        assert metadata.overlap_chars == 0
        assert metadata.page_number is None
        assert metadata.section_path is None
        assert metadata.has_table is False
        assert metadata.table_id is None
        assert isinstance(metadata.created_at, datetime)

    def test_create_metadata_with_page_number(self):
        """Test creating metadata with a page_number value."""
        metadata = EmbeddingMetadata(page_number=5)

        assert metadata.page_number == 5

    def test_page_number_included_in_model_dump(self):
        """Test that page_number is present in model_dump output."""
        metadata = EmbeddingMetadata(page_number=3)

        result = metadata.model_dump(mode="json")

        assert result["page_number"] == 3

    def test_page_number_none_in_model_dump(self):
        """Test that page_number=None is serialized correctly."""
        metadata = EmbeddingMetadata()

        result = metadata.model_dump(mode="json")

        assert result["page_number"] is None

    def test_page_number_roundtrip(self):
        """Test page_number survives model_dump -> model_validate roundtrip."""
        original = EmbeddingMetadata(page_number=7)

        data = original.model_dump(mode="json")
        restored = EmbeddingMetadata.model_validate(data)

        assert restored.page_number == 7

    def test_create_custom_metadata(self):
        """Test creating metadata with custom values."""
        metadata = EmbeddingMetadata(
            model_version="text-embedding-3-small",
            token_count=128,
            chunking_strategy="fixed_size",
            chunk_size=512,
            overlap_chars=50,
        )

        assert metadata.model_version == "text-embedding-3-small"
        assert metadata.token_count == 128
        assert metadata.chunking_strategy == "fixed_size"
        assert metadata.chunk_size == 512
        assert metadata.overlap_chars == 50

    def test_create_metadata_with_structure_aware_fields(self):
        """Test creating metadata with section_path, has_table, table_id."""
        metadata = EmbeddingMetadata(
            model_version="text-embedding-3-small",
            token_count=200,
            chunking_strategy="markdown_aware",
            section_path=["Introduction", "Background"],
            has_table=True,
            table_id="table_0",
        )

        assert metadata.section_path == ["Introduction", "Background"]
        assert metadata.has_table is True
        assert metadata.table_id == "table_0"

    def test_model_dump(self):
        """Test converting metadata to dictionary via model_dump."""
        metadata = EmbeddingMetadata(
            model_version="text-embedding-3-small",
            token_count=128,
            chunking_strategy="fixed_size",
            chunk_size=512,
            overlap_chars=50,
        )

        result = metadata.model_dump(mode="json")

        assert result["model_version"] == "text-embedding-3-small"
        assert result["token_count"] == 128
        assert result["chunking_strategy"] == "fixed_size"
        assert result["chunk_size"] == 512
        assert result["overlap_chars"] == 50
        assert result["section_path"] is None
        assert result["has_table"] is False
        assert result["table_id"] is None
        assert "created_at" in result

    def test_model_dump_with_structure_aware_fields(self):
        """Test model_dump includes section_path, has_table, table_id."""
        metadata = EmbeddingMetadata(
            section_path=["Chapter 1", "Section A"],
            has_table=True,
            table_id="table_2",
        )

        result = metadata.model_dump(mode="json")

        assert result["section_path"] == ["Chapter 1", "Section A"]
        assert result["has_table"] is True
        assert result["table_id"] == "table_2"

    def test_model_validate(self):
        """Test creating metadata from dictionary via model_validate."""
        data = {
            "model_version": "text-embedding-3-large",
            "token_count": 256,
            "chunking_strategy": "semantic_chunking",
            "chunk_size": 1024,
            "overlap_chars": 100,
            "created_at": "2026-01-28T10:00:00",
        }

        metadata = EmbeddingMetadata.model_validate(data)

        assert metadata.model_version == "text-embedding-3-large"
        assert metadata.token_count == 256
        assert metadata.chunking_strategy == "semantic_chunking"
        assert metadata.chunk_size == 1024
        assert metadata.overlap_chars == 100

    def test_model_validate_with_structure_aware_fields(self):
        """Test model_validate parses section_path, has_table, table_id."""
        data = {
            "model_version": "text-embedding-3-small",
            "token_count": 150,
            "chunking_strategy": "markdown_aware",
            "section_path": ["Chapter 1", "Background"],
            "has_table": True,
            "table_id": "table_1",
            "created_at": "2026-01-28T10:00:00",
        }

        metadata = EmbeddingMetadata.model_validate(data)

        assert metadata.section_path == ["Chapter 1", "Background"]
        assert metadata.has_table is True
        assert metadata.table_id == "table_1"

    def test_model_validate_with_defaults(self):
        """Test creating metadata from empty dictionary uses defaults."""
        metadata = EmbeddingMetadata.model_validate({})

        assert metadata.model_version == ""
        assert metadata.token_count == 0
        assert metadata.chunking_strategy == ""
        assert metadata.section_path is None
        assert metadata.has_table is False
        assert metadata.table_id is None

    def test_roundtrip_with_structure_aware_fields(self):
        """Test model_dump -> model_validate roundtrip preserves structure-aware fields."""
        original = EmbeddingMetadata(
            model_version="text-embedding-3-small",
            token_count=200,
            chunking_strategy="markdown_aware",
            chunk_size=1024,
            section_path=["Intro", "Methods", "Results"],
            has_table=True,
            table_id="table_0",
        )

        data = original.model_dump(mode="json")
        restored = EmbeddingMetadata.model_validate(data)

        assert restored.section_path == ["Intro", "Methods", "Results"]
        assert restored.has_table is True
        assert restored.table_id == "table_0"
        assert restored.chunking_strategy == "markdown_aware"


class TestEmbedding:
    """Tests for Embedding entity."""

    def test_create_embedding(self):
        """Test creating an embedding entity."""
        embedding = Embedding(
            file_id="file-123",
            chunk_id="file-123_chunk_0",
            embedding_model="text-embedding-3-small",
            embedding_dimension=1536,
            vector=[0.1, -0.2, 0.3] * 512,  # 1536 dimensions
            chunk_text="This is sample text content.",
        )

        assert embedding.file_id == "file-123"
        assert embedding.chunk_id == "file-123_chunk_0"
        assert embedding.embedding_model == "text-embedding-3-small"
        assert embedding.embedding_dimension == 1536
        assert len(embedding.vector) == 1536
        assert embedding.chunk_text == "This is sample text content."

    def test_vector_preview_property(self):
        """Test vector_preview property returns first 5 elements."""
        vector = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
        embedding = Embedding(
            file_id="file-123",
            chunk_id="file-123_chunk_0",
            embedding_model="text-embedding-3-small",
            embedding_dimension=8,
            vector=vector,
            chunk_text="Test text",
        )

        assert embedding.vector_preview == [0.1, 0.2, 0.3, 0.4, 0.5]

    def test_vector_preview_property_short_vector(self):
        """Test vector_preview with vector shorter than 5 elements."""
        vector = [0.1, 0.2, 0.3]
        embedding = Embedding(
            file_id="file-123",
            chunk_id="file-123_chunk_0",
            embedding_model="test-model",
            embedding_dimension=3,
            vector=vector,
            chunk_text="Test text",
        )

        assert embedding.vector_preview == [0.1, 0.2, 0.3]

    def test_chunk_text_preview_property(self):
        """Test chunk_text_preview property with short text."""
        embedding = Embedding(
            file_id="file-123",
            chunk_id="file-123_chunk_0",
            embedding_model="text-embedding-3-small",
            embedding_dimension=1536,
            vector=[0.1] * 1536,
            chunk_text="Short text",
        )

        assert embedding.chunk_text_preview == "Short text"

    def test_chunk_text_preview_property_long_text(self):
        """Test chunk_text_preview property truncates long text."""
        long_text = "A" * 200
        embedding = Embedding(
            file_id="file-123",
            chunk_id="file-123_chunk_0",
            embedding_model="text-embedding-3-small",
            embedding_dimension=1536,
            vector=[0.1] * 1536,
            chunk_text=long_text,
        )

        assert len(embedding.chunk_text_preview) == 100
        assert embedding.chunk_text_preview == "A" * 100

    def test_model_dump(self):
        """Test converting embedding to dictionary via model_dump."""
        embedding = Embedding(
            file_id="file-123",
            chunk_id="file-123_chunk_0",
            embedding_model="text-embedding-3-small",
            embedding_dimension=8,
            vector=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
            chunk_text="Sample text",
            metadata=EmbeddingMetadata(token_count=3),
        )

        result = embedding.model_dump(mode="json")

        assert result["file_id"] == "file-123"
        assert result["chunk_id"] == "file-123_chunk_0"
        assert result["embedding_model"] == "text-embedding-3-small"
        assert result["embedding_dimension"] == 8
        assert result["vector"] == [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
        assert result["chunk_text"] == "Sample text"
        assert "metadata" in result
        assert result["metadata"]["token_count"] == 3

    def test_model_validate(self):
        """Test creating embedding from dictionary via model_validate."""
        data = {
            "file_id": "file-456",
            "chunk_id": "file-456_chunk_1",
            "embedding_model": "text-embedding-3-large",
            "embedding_dimension": 3072,
            "vector": [0.1] * 3072,
            "chunk_text": "More content",
            "metadata": {
                "model_version": "text-embedding-3-large",
                "token_count": 256,
            },
        }

        embedding = Embedding.model_validate(data)

        assert embedding.file_id == "file-456"
        assert embedding.chunk_id == "file-456_chunk_1"
        assert embedding.embedding_model == "text-embedding-3-large"
        assert embedding.embedding_dimension == 3072
        assert len(embedding.vector) == 3072
        assert embedding.metadata.model_version == "text-embedding-3-large"
        assert embedding.metadata.token_count == 256

    def test_model_dump_roundtrip(self):
        """Test embedding roundtrip via model_dump/model_validate."""
        embedding = Embedding(
            file_id="file-123",
            chunk_id="file-123_chunk_0",
            embedding_model="text-embedding-3-small",
            embedding_dimension=8,
            vector=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
            chunk_text="Storage test",
        )

        result = embedding.model_dump(mode="json")

        assert result["file_id"] == "file-123"
        assert result["embedding_model"] == "text-embedding-3-small"
        assert result["vector"] == [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]

    def test_model_validate_from_json_dict(self):
        """Test creating embedding from JSON-like dictionary."""
        data = {
            "file_id": "file-789",
            "chunk_id": "file-789_chunk_0",
            "embedding_model": "text-embedding-3-small",
            "embedding_dimension": 1536,
            "vector": [0.1] * 1536,
            "chunk_text": "Loaded from storage",
        }

        embedding = Embedding.model_validate(data)

        assert embedding.file_id == "file-789"
        assert embedding.chunk_text == "Loaded from storage"
        assert len(embedding.vector) == 1536

    def test_embedding_with_metadata(self):
        """Test creating embedding with full metadata."""
        metadata = EmbeddingMetadata(
            model_version="text-embedding-3-small",
            token_count=100,
            chunking_strategy="fixed_size",
            chunk_size=512,
            overlap_chars=50,
        )
        embedding = Embedding(
            file_id="file-123",
            chunk_id="file-123_chunk_0",
            embedding_model="text-embedding-3-small",
            embedding_dimension=1536,
            vector=[0.1] * 1536,
            chunk_text="Test with metadata",
            metadata=metadata,
        )

        assert embedding.metadata.model_version == "text-embedding-3-small"
        assert embedding.metadata.token_count == 100
        assert embedding.metadata.chunking_strategy == "fixed_size"
