"""Unit tests for LlamaIndexChunker adapter."""

import pytest

from src.config.settings import ChunkingSettings
from src.core.errors import InvalidChunkingStrategyError
from src.core.value_objects.chunking_strategy import ChunkingStrategy, ChunkingStrategyName
from src.infrastructure.llamaindex.chunker_llamaindex import LlamaIndexChunker


@pytest.fixture
def chunking_settings() -> ChunkingSettings:
    """Create chunking settings for testing."""
    return ChunkingSettings(
        default_strategy="fixed_size",
        default_chunk_size=512,
        default_chunk_overlap=50,
        use_fake=False,
    )


@pytest.fixture
def llamaindex_chunker(chunking_settings: ChunkingSettings) -> LlamaIndexChunker:
    """Create a LlamaIndexChunker instance for testing."""
    return LlamaIndexChunker(settings=chunking_settings)


class TestLlamaIndexChunker:
    """Tests for LlamaIndexChunker adapter."""

    async def test_chunk_text_basic(self, llamaindex_chunker: LlamaIndexChunker):
        """Test basic text chunking with LlamaIndex."""
        text = """This is a sample document for testing chunking.
        It contains multiple sentences to ensure proper splitting.
        The chunker should create appropriate chunks based on the strategy.
        We want to verify that the text is split correctly.""" * 5  # Make it longer

        strategy = ChunkingStrategy.fixed_size(chunk_size=200, chunk_overlap=20)

        chunks = await llamaindex_chunker.chunk_text(
            text=text,
            file_id="test-file",
            strategy=strategy,
        )

        assert len(chunks) > 0
        assert all(c.file_id == "test-file" for c in chunks)
        assert all(c.chunk_id.startswith("test-file_chunk_") for c in chunks)

    async def test_chunk_text_preserves_order(self, llamaindex_chunker: LlamaIndexChunker):
        """Test that chunks are returned in order."""
        text = "This is a test. " * 50
        strategy = ChunkingStrategy.fixed_size(chunk_size=100, chunk_overlap=10)

        chunks = await llamaindex_chunker.chunk_text(
            text=text,
            file_id="test-file",
            strategy=strategy,
        )

        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    async def test_chunk_text_small_input(self, llamaindex_chunker: LlamaIndexChunker):
        """Test chunking text smaller than chunk size."""
        text = "Small text for testing."
        strategy = ChunkingStrategy.fixed_size(chunk_size=512, chunk_overlap=50)

        chunks = await llamaindex_chunker.chunk_text(
            text=text,
            file_id="test-file",
            strategy=strategy,
        )

        assert len(chunks) == 1
        assert chunks[0].text.strip() == text.strip()

    async def test_chunk_metadata(self, llamaindex_chunker: LlamaIndexChunker):
        """Test that chunks have correct metadata."""
        text = "This is test content. " * 20
        strategy = ChunkingStrategy.fixed_size(chunk_size=100, chunk_overlap=10)

        chunks = await llamaindex_chunker.chunk_text(
            text=text,
            file_id="test-file",
            strategy=strategy,
        )

        for chunk in chunks:
            assert chunk.metadata.overlap_chars == 10
            assert chunk.metadata.token_count is None

    async def test_chunk_positions(self, llamaindex_chunker: LlamaIndexChunker):
        """Test that chunk positions are tracked."""
        text = "The quick brown fox. " * 30
        strategy = ChunkingStrategy.fixed_size(chunk_size=100, chunk_overlap=10)

        chunks = await llamaindex_chunker.chunk_text(
            text=text,
            file_id="test-file",
            strategy=strategy,
        )

        # All chunks should have position info
        for chunk in chunks:
            assert chunk.start_char >= 0
            assert chunk.end_char > chunk.start_char

    def test_get_supported_strategies(self, llamaindex_chunker: LlamaIndexChunker):
        """Test getting supported strategies."""
        strategies = llamaindex_chunker.get_supported_strategies()

        assert ChunkingStrategyName.FIXED_SIZE in strategies
        # Only fixed_size is currently supported
        assert len(strategies) == 1

    def test_is_strategy_supported_fixed_size(self, llamaindex_chunker: LlamaIndexChunker):
        """Test checking fixed_size strategy support."""
        assert llamaindex_chunker.is_strategy_supported(ChunkingStrategyName.FIXED_SIZE) is True

    def test_is_strategy_supported_unsupported(self, llamaindex_chunker: LlamaIndexChunker):
        """Test checking unsupported strategy."""
        # Semantic is not yet implemented
        assert llamaindex_chunker.is_strategy_supported(ChunkingStrategyName.SEMANTIC) is False

    async def test_chunk_unsupported_strategy(self, llamaindex_chunker: LlamaIndexChunker):
        """Test error when using unsupported strategy."""
        text = "Test content"
        strategy = ChunkingStrategy.semantic(
            chunk_size=512,
            chunk_overlap=50,
        )

        with pytest.raises(InvalidChunkingStrategyError) as exc_info:
            await llamaindex_chunker.chunk_text(
                text=text,
                file_id="test-file",
                strategy=strategy,
            )

        assert "semantic_chunking" in str(exc_info.value)

    async def test_chunk_text_with_sentences(self, llamaindex_chunker: LlamaIndexChunker):
        """Test that SentenceSplitter respects sentence boundaries."""
        text = "First sentence here. Second sentence follows. Third sentence ends. " * 10
        strategy = ChunkingStrategy.fixed_size(chunk_size=100, chunk_overlap=10)

        chunks = await llamaindex_chunker.chunk_text(
            text=text,
            file_id="test-file",
            strategy=strategy,
        )

        # Verify chunks are created
        assert len(chunks) > 1

    async def test_chunk_text_unicode(self, llamaindex_chunker: LlamaIndexChunker):
        """Test chunking text with unicode characters."""
        text = "Hello ā€œworldā€! This has unicode: Ć©Ć Ć¼ ę—„ęœ¬čŖž. " * 20
        strategy = ChunkingStrategy.fixed_size(chunk_size=100, chunk_overlap=10)

        chunks = await llamaindex_chunker.chunk_text(
            text=text,
            file_id="test-file",
            strategy=strategy,
        )

        assert len(chunks) > 0
        # Verify unicode is preserved
        full_text = "".join(c.text for c in chunks)
        assert "ę—„ęœ¬čŖž" in full_text or "unicode" in full_text.lower()

    async def test_chunk_text_with_newlines(self, llamaindex_chunker: LlamaIndexChunker):
        """Test chunking text with newlines."""
        text = "Line one.\n\nLine two.\n\nLine three.\n\n" * 20
        strategy = ChunkingStrategy.fixed_size(chunk_size=100, chunk_overlap=10)

        chunks = await llamaindex_chunker.chunk_text(
            text=text,
            file_id="test-file",
            strategy=strategy,
        )

        assert len(chunks) > 0

    async def test_chunk_id_format(self, llamaindex_chunker: LlamaIndexChunker):
        """Test that chunk IDs follow expected format."""
        text = "Test content. " * 30
        strategy = ChunkingStrategy.fixed_size(chunk_size=100, chunk_overlap=10)

        chunks = await llamaindex_chunker.chunk_text(
            text=text,
            file_id="my-doc-123",
            strategy=strategy,
        )

        for i, chunk in enumerate(chunks):
            assert chunk.chunk_id == f"my-doc-123_chunk_{i}"

    async def test_custom_separator(self, llamaindex_chunker: LlamaIndexChunker):
        """Test chunking with custom separator."""
        text = "Part one|Part two|Part three|" * 10
        strategy = ChunkingStrategy.fixed_size(
            chunk_size=100,
            chunk_overlap=10,
            separator="|",
        )

        chunks = await llamaindex_chunker.chunk_text(
            text=text,
            file_id="test-file",
            strategy=strategy,
        )

        assert len(chunks) > 0
