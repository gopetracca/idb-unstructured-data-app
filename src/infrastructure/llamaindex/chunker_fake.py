"""Fake implementation of the chunker port for testing."""

import asyncio
import logging
from datetime import datetime

from src.application.ports.chunker import ChunkerPort
from src.core.entities.chunk import Chunk, ChunkMetadata
from src.core.errors import ChunkingError, InvalidChunkingStrategyError
from src.core.value_objects.chunking_strategy import ChunkingStrategy, ChunkingStrategyName

logger = logging.getLogger(__name__)


class FakeChunker(ChunkerPort):
    """
    Fake implementation of document chunking for testing.

    Provides a simple character-based chunking without external dependencies.
    Useful for unit tests and local development.
    """

    def __init__(self, simulated_delay_seconds: float = 0.0) -> None:
        """
        Initialize the fake chunker.

        Args:
            simulated_delay_seconds: Optional delay to simulate processing time
        """
        self._simulated_delay = simulated_delay_seconds
        self._supported_strategies = [
            ChunkingStrategyName.FIXED_SIZE,
            ChunkingStrategyName.SEMANTIC,
            ChunkingStrategyName.MARKDOWN_AWARE,
            ChunkingStrategyName.RECURSIVE,
        ]

    async def chunk_text(
        self,
        text: str,
        file_id: str,
        strategy: ChunkingStrategy,
    ) -> list[Chunk]:
        """
        Chunk text content using simple character-based splitting.

        Args:
            text: The text content to chunk
            file_id: Unique identifier for the parent file
            strategy: Chunking strategy configuration

        Returns:
            List of Chunk objects

        Raises:
            ChunkingError: If chunking fails
            InvalidChunkingStrategyError: If strategy is not supported
        """
        if not self.is_strategy_supported(strategy.strategy_name):
            raise InvalidChunkingStrategyError(
                strategy_name=strategy.strategy_name.value,
                supported_strategies=[s.value for s in self.get_supported_strategies()],
            )

        # Simulate processing delay
        if self._simulated_delay > 0:
            await asyncio.sleep(self._simulated_delay)

        try:
            chunks = []
            chunk_size = strategy.chunk_size
            chunk_overlap = strategy.chunk_overlap
            text_length = len(text)

            if text_length == 0:
                logger.warning("Empty text provided for chunking: file_id=%s", file_id)
                return chunks

            # Simple character-based chunking with overlap
            start = 0
            chunk_index = 0

            while start < text_length:
                # Calculate end position
                end = min(start + chunk_size, text_length)

                # Extract chunk text
                chunk_text = text[start:end]

                # Create chunk metadata
                metadata = ChunkMetadata(
                    overlap_chars=chunk_overlap,
                    token_count=None,
                    created_at=datetime.utcnow(),
                )

                # Create chunk
                chunk = Chunk(
                    file_id=file_id,
                    chunk_id=f"{file_id}_chunk_{chunk_index}",
                    chunk_index=chunk_index,
                    text=chunk_text,
                    start_char=start,
                    end_char=end,
                    page_number=None,
                    metadata=metadata,
                )
                chunks.append(chunk)

                # Move to next chunk position (accounting for overlap)
                if end >= text_length:
                    break

                start = end - chunk_overlap
                if start <= chunks[-1].start_char:
                    # Prevent infinite loop if overlap >= chunk_size
                    start = end

                chunk_index += 1

            logger.info(
                f"Fake chunker created {len(chunks)} chunks: "
                f"file_id={file_id}, strategy={strategy.strategy_name.value}"
            )

            return chunks

        except Exception as e:
            logger.error(
                f"Fake chunking failed: file_id={file_id}, error={str(e)}",
                exc_info=True,
            )
            raise ChunkingError(
                message=f"Failed to chunk text: {str(e)}",
                file_id=file_id,
                strategy=strategy.strategy_name.value,
            ) from e

    def get_supported_strategies(self) -> list[ChunkingStrategyName]:
        """Get list of supported chunking strategies."""
        return self._supported_strategies
