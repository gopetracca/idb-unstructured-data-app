"""LlamaIndex implementation of the chunker port."""

import logging
from datetime import datetime
from typing import Callable

from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document, TextNode

from src.application.ports.chunker import ChunkerPort
from src.config.settings import ChunkingSettings
from src.core.entities.chunk import Chunk, ChunkMetadata
from src.core.errors import ChunkingError, InvalidChunkingStrategyError
from src.core.value_objects.chunking_strategy import ChunkingStrategy, ChunkingStrategyName

logger = logging.getLogger(__name__)


class LlamaIndexChunker(ChunkerPort):
    """
    LlamaIndex implementation of document chunking operations.

    Uses LlamaIndex's node parsers for chunking text content.
    Currently supports:
    - fixed_size: SentenceSplitter for uniform chunks
    """

    def __init__(self, settings: ChunkingSettings) -> None:
        """
        Initialize the LlamaIndex chunker.

        Args:
            settings: Chunking configuration settings
        """
        self._settings = settings
        self._parser_factories: dict[ChunkingStrategyName, Callable] = {
            ChunkingStrategyName.FIXED_SIZE: self._create_sentence_splitter,
        }

    async def chunk_text(
        self,
        text: str,
        file_id: str,
        strategy: ChunkingStrategy,
    ) -> list[Chunk]:
        """
        Chunk text content using LlamaIndex node parser.

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

        try:
            # Get the appropriate parser
            parser = self._get_parser(strategy)

            # Create a LlamaIndex Document
            document = Document(text=text, id_=file_id)

            # Parse into nodes
            nodes = parser.get_nodes_from_documents([document])

            # Convert nodes to Chunk entities
            chunks = []
            for i, node in enumerate(nodes):
                chunk = self._node_to_chunk(
                    node=node,
                    file_id=file_id,
                    chunk_index=i,
                    strategy=strategy,
                )
                chunks.append(chunk)

            logger.info(
                f"Chunked text with LlamaIndex: file_id={file_id}, "
                f"strategy={strategy.strategy_name.value}, "
                f"chunk_count={len(chunks)}"
            )

            return chunks

        except InvalidChunkingStrategyError:
            raise

        except Exception as e:
            logger.error(
                f"LlamaIndex chunking failed: file_id={file_id}, error={str(e)}",
                exc_info=True,
            )
            raise ChunkingError(
                message=f"Failed to chunk text with LlamaIndex: {str(e)}",
                file_id=file_id,
                strategy=strategy.strategy_name.value,
            ) from e

    def get_supported_strategies(self) -> list[ChunkingStrategyName]:
        """Get list of supported chunking strategies."""
        return list(self._parser_factories.keys())

    def _get_parser(self, strategy: ChunkingStrategy):
        """Get the appropriate parser for the strategy."""
        factory = self._parser_factories.get(strategy.strategy_name)
        if factory is None:
            raise InvalidChunkingStrategyError(
                strategy_name=strategy.strategy_name.value,
                supported_strategies=[s.value for s in self.get_supported_strategies()],
            )
        return factory(strategy)

    def _create_sentence_splitter(self, strategy: ChunkingStrategy) -> SentenceSplitter:
        """Create a SentenceSplitter for fixed-size chunking."""
        return SentenceSplitter(
            chunk_size=strategy.chunk_size,
            chunk_overlap=strategy.chunk_overlap,
            separator=strategy.separator or " ",
        )

    def _node_to_chunk(
        self,
        node: TextNode,
        file_id: str,
        chunk_index: int,
        strategy: ChunkingStrategy,
    ) -> Chunk:
        """Convert a LlamaIndex TextNode to a Chunk entity."""
        # Get character positions from node metadata
        start_char = node.start_char_idx if node.start_char_idx is not None else 0
        end_char = node.end_char_idx if node.end_char_idx is not None else len(node.text)

        # Extract page number from node metadata if available
        page_number = None
        if node.metadata:
            page_number = node.metadata.get("page_number") or node.metadata.get("page_label")
            if page_number is not None:
                try:
                    page_number = int(page_number)
                except (ValueError, TypeError):
                    page_number = None

        # Create chunk metadata
        metadata = ChunkMetadata(
            overlap_chars=strategy.chunk_overlap,
            token_count=None,  # Could be calculated with tiktoken if needed
            created_at=datetime.utcnow(),
        )

        return Chunk(
            file_id=file_id,
            chunk_id=f"{file_id}_chunk_{chunk_index}",
            chunk_index=chunk_index,
            text=node.text,
            start_char=start_char,
            end_char=end_char,
            page_number=page_number,
            metadata=metadata,
        )
