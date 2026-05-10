"""Port interface for document chunking service."""

from abc import ABC, abstractmethod

from src.core.entities.chunk import Chunk
from src.core.value_objects.chunking_strategy import ChunkingStrategy, ChunkingStrategyName


class ChunkerPort(ABC):
    """
    Abstract interface for document chunking operations.

    This port defines the contract that any chunking implementation
    must fulfill, allowing for both fake (testing) and real (LlamaIndex)
    implementations.
    """

    @abstractmethod
    async def chunk_text(
        self,
        text: str,
        file_id: str,
        strategy: ChunkingStrategy,
    ) -> list[Chunk]:
        """
        Chunk text content according to the specified strategy.

        Args:
            text: The text content to chunk
            file_id: Unique identifier for the parent file
            strategy: Chunking strategy configuration

        Returns:
            List of Chunk objects representing the chunked text

        Raises:
            ChunkingError: If chunking fails
            InvalidChunkingStrategyError: If strategy is not supported
        """
        pass

    @abstractmethod
    def get_supported_strategies(self) -> list[ChunkingStrategyName]:
        """
        Get list of supported chunking strategies.

        Returns:
            List of supported strategy names
        """
        pass

    def is_strategy_supported(self, strategy_name: ChunkingStrategyName) -> bool:
        """
        Check if a chunking strategy is supported.

        Args:
            strategy_name: The strategy name to check

        Returns:
            True if strategy is supported, False otherwise
        """
        return strategy_name in self.get_supported_strategies()
