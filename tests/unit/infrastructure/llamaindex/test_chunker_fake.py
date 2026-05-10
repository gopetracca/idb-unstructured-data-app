"""Unit tests for FakeChunker adapter."""

import pytest

from src.core.errors import InvalidChunkingStrategyError
from src.core.value_objects.chunking_strategy import ChunkingStrategy, ChunkingStrategyName
from src.infrastructure.llamaindex.chunker_fake import FakeChunker


@pytest.fixture
def fake_chunker() -> FakeChunker:
    """Create a FakeChunker instance for testing."""
    return FakeChunker(simulated_delay_seconds=0.0)


class TestFakeChunker:
    """Tests for FakeChunker adapter."""

    async def test_chunk_text_basic(self, fake_chunker: FakeChunker):
        """Test basic text chunking."""
        text = "A" * 1000  # 1000 character text
        strategy = ChunkingStrategy.fixed_size(chunk_size=500, chunk_overlap=50)

        chunks = await fake_chunker.chunk_text(
            text=text,
            file_id="test-file",
            strategy=strategy,
        )

        assert len(chunks) > 0
        assert all(c.file_id == "test-file" for c in chunks)
        assert all(c.chunk_id.startswith("test-file_chunk_") for c in chunks)

    async def test_chunk_text_preserves_order(self, fake_chunker: FakeChunker):
        """Test that chunks are returned in order."""
        text = "A" * 1000
        strategy = ChunkingStrategy.fixed_size(chunk_size=200, chunk_overlap=20)

        chunks = await fake_chunker.chunk_text(
            text=text,
            file_id="test-file",
            strategy=strategy,
        )

        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    async def test_chunk_text_overlap(self, fake_chunker: FakeChunker):
        """Test that chunks have proper overlap."""
        text = "A" * 500
        strategy = ChunkingStrategy.fixed_size(chunk_size=200, chunk_overlap=50)

        chunks = await fake_chunker.chunk_text(
            text=text,
            file_id="test-file",
            strategy=strategy,
        )

        # With 500 chars, 200 chunk size, 50 overlap:
        # Chunk 0: 0-200
        # Chunk 1: 150-350
        # Chunk 2: 300-500
        assert len(chunks) >= 2

        # Check overlap between consecutive chunks
        for i in range(len(chunks) - 1):
            current_end = chunks[i].end_char
            next_start = chunks[i + 1].start_char
            assert current_end > next_start  # Should overlap

    async def test_chunk_text_empty_input(self, fake_chunker: FakeChunker):
        """Test chunking empty text."""
        strategy = ChunkingStrategy.fixed_size(chunk_size=512, chunk_overlap=50)

        chunks = await fake_chunker.chunk_text(
            text="",
            file_id="test-file",
            strategy=strategy,
        )

        assert chunks == []

    async def test_chunk_text_small_input(self, fake_chunker: FakeChunker):
        """Test chunking text smaller than chunk size."""
        text = "Small text"
        strategy = ChunkingStrategy.fixed_size(chunk_size=512, chunk_overlap=50)

        chunks = await fake_chunker.chunk_text(
            text=text,
            file_id="test-file",
            strategy=strategy,
        )

        assert len(chunks) == 1
        assert chunks[0].text == text

    async def test_chunk_text_exact_chunk_size(self, fake_chunker: FakeChunker):
        """Test chunking text exactly equal to chunk size."""
        text = "A" * 512
        strategy = ChunkingStrategy.fixed_size(chunk_size=512, chunk_overlap=50)

        chunks = await fake_chunker.chunk_text(
            text=text,
            file_id="test-file",
            strategy=strategy,
        )

        assert len(chunks) == 1
        assert len(chunks[0].text) == 512

    async def test_chunk_metadata(self, fake_chunker: FakeChunker):
        """Test that chunks have correct metadata."""
        text = "A" * 1000
        strategy = ChunkingStrategy.fixed_size(chunk_size=512, chunk_overlap=50)

        chunks = await fake_chunker.chunk_text(
            text=text,
            file_id="test-file",
            strategy=strategy,
        )

        for chunk in chunks:
            assert chunk.metadata.overlap_chars == 50
            assert chunk.metadata.token_count is None

    async def test_chunk_positions(self, fake_chunker: FakeChunker):
        """Test that chunk positions are correct."""
        text = "A" * 200  # 200 characters
        strategy = ChunkingStrategy.fixed_size(chunk_size=100, chunk_overlap=20)

        chunks = await fake_chunker.chunk_text(
            text=text,
            file_id="test-file",
            strategy=strategy,
        )

        # First chunk: 0-100
        assert chunks[0].start_char == 0
        assert chunks[0].end_char == 100
        assert len(chunks[0].text) == 100

    def test_get_supported_strategies(self, fake_chunker: FakeChunker):
        """Test getting supported strategies."""
        strategies = fake_chunker.get_supported_strategies()

        assert ChunkingStrategyName.FIXED_SIZE in strategies
        assert ChunkingStrategyName.SEMANTIC in strategies
        assert ChunkingStrategyName.MARKDOWN_AWARE in strategies
        assert ChunkingStrategyName.RECURSIVE in strategies

    def test_is_strategy_supported(self, fake_chunker: FakeChunker):
        """Test checking strategy support."""
        assert fake_chunker.is_strategy_supported(ChunkingStrategyName.FIXED_SIZE) is True
        assert fake_chunker.is_strategy_supported(ChunkingStrategyName.SEMANTIC) is True

    async def test_chunk_all_strategies(self, fake_chunker: FakeChunker):
        """Test that all supported strategies work."""
        text = "A" * 500

        for strategy_name in fake_chunker.get_supported_strategies():
            strategy = ChunkingStrategy.model_validate(
                {
                    "strategy_name": strategy_name.value,
                    "parameters": {
                        "chunk_size": 200,
                        "chunk_overlap": 20,
                    },
                }
            )

            chunks = await fake_chunker.chunk_text(
                text=text,
                file_id="test-file",
                strategy=strategy,
            )

            assert len(chunks) > 0

    async def test_simulated_delay(self):
        """Test that simulated delay works."""
        import time

        chunker = FakeChunker(simulated_delay_seconds=0.1)
        strategy = ChunkingStrategy.fixed_size()

        start = time.time()
        await chunker.chunk_text(
            text="Test",
            file_id="test-file",
            strategy=strategy,
        )
        elapsed = time.time() - start

        assert elapsed >= 0.1
