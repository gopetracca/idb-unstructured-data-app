"""Chonkie implementation of the chunker port for structure-aware chunking."""

import asyncio
import logging
from datetime import datetime, timezone

import tiktoken
from chonkie import RecursiveChunker, SemanticChunker, TokenChunker
from chonkie.types.recursive import RecursiveLevel, RecursiveRules

from src.application.ports.chunker import ChunkerPort
from src.config.settings import ChunkingSettings
from src.core.entities.chunk import Chunk, ChunkMetadata
from src.core.errors import ChunkingError, InvalidChunkingStrategyError
from src.core.value_objects.chunking_strategy import ChunkingStrategy, ChunkingStrategyName
from src.infrastructure.chonkie.metadata import (
    HeadingTracker,
    PageTracker,
    count_tokens,
    get_tiktoken_encoding,
)
from src.infrastructure.chonkie.table_handler import (
    TableBlock,
    extract_tables,
    get_placeholder_pattern,
)

# Vendored rules from chonkie-ai/recipes::recipes/markdown_en.json (schema v1, version 0.1.0).
# Inlined to avoid a runtime HuggingFace download, making MARKDOWN_AWARE fully offline.
_MARKDOWN_EN_RULES = RecursiveRules(
    levels=[
        RecursiveLevel(delimiters=["######", "#####", "####", "###", "##", "#"], whitespace=False, include_delim="next"),
        RecursiveLevel(delimiters=["\n\n", "\n\r"], whitespace=False, include_delim="prev"),
        RecursiveLevel(delimiters=["\n", "\r"], whitespace=False, include_delim="prev"),
        RecursiveLevel(delimiters=[". ", "! ", "? "], whitespace=False, include_delim="prev"),
        RecursiveLevel(delimiters=None, whitespace=False, include_delim="prev"),
    ]
)

logger = logging.getLogger(__name__)


class ChonkieChunker(ChunkerPort):
    """Structure-aware chunking adapter using the Chonkie library.

    Supports up to four strategies:
    - FIXED_SIZE: Token-based fixed-size chunking using TokenChunker
    - MARKDOWN_AWARE: Heading-aware structural chunking using RecursiveChunker with markdown recipe
    - RECURSIVE: Recursive chunking with custom markdown-aware rules
    - SEMANTIC: Embedding-based boundary detection using SemanticChunker (disabled by default)

    All strategies extract HTML tables as atomic chunks before processing text.
    The tokenizer (cl100k_base) is pre-loaded once at construction so no outbound
    network calls are made at runtime for token-based strategies.
    """

    def __init__(self, settings: ChunkingSettings) -> None:
        self._settings = settings

        try:
            self._tokenizer: tiktoken.Encoding = get_tiktoken_encoding("cl100k_base")
        except Exception as e:
            raise RuntimeError(
                "Failed to load cl100k_base tiktoken encoding during ChonkieChunker init. "
                "If running offline, ensure TIKTOKEN_CACHE_DIR is set and the cache is "
                "populated at image build time."
            ) from e

        supported: list[ChunkingStrategyName] = [
            ChunkingStrategyName.FIXED_SIZE,
            ChunkingStrategyName.MARKDOWN_AWARE,
            ChunkingStrategyName.RECURSIVE,
        ]
        if settings.enable_semantic_chunking:
            supported.append(ChunkingStrategyName.SEMANTIC)
        self._supported_strategies: list[ChunkingStrategyName] = supported

        # Cached chunker instances keyed by (strategy_name, chunk_size, chunk_overlap)
        self._chunker_cache: dict[
            tuple[str, int, int], TokenChunker | RecursiveChunker | SemanticChunker
        ] = {}

    async def chunk_text(
        self,
        text: str,
        file_id: str,
        strategy: ChunkingStrategy,
    ) -> list[Chunk]:
        if not self.is_strategy_supported(strategy.strategy_name):
            raise InvalidChunkingStrategyError(
                strategy_name=strategy.strategy_name.value,
                supported_strategies=[s.value for s in self.get_supported_strategies()],
            )

        try:
            # Step 1: Extract HTML tables, replace with placeholders
            text_without_tables, tables = extract_tables(text)

            # Build trackers on the ORIGINAL text for accurate section paths and page numbers
            heading_tracker = HeadingTracker(text)
            page_tracker = PageTracker(text)

            # Step 2: Chunk the text (without tables) using the appropriate strategy
            # Offload CPU-bound chunking to a thread to avoid blocking the event loop
            raw_chunks = await asyncio.to_thread(
                self._chunk_with_strategy, text_without_tables, strategy
            )

            # Step 3: Build final chunk list, reinserting table chunks at correct positions
            chunks = self._build_chunks(
                raw_chunks=raw_chunks,
                tables=tables,
                text_without_tables=text_without_tables,
                original_text=text,
                file_id=file_id,
                strategy=strategy,
                heading_tracker=heading_tracker,
                page_tracker=page_tracker,
            )

            logger.info(
                f"Chunked text with Chonkie: file_id={file_id}, "
                f"strategy={strategy.strategy_name.value}, "
                f"chunk_count={len(chunks)}, table_count={len(tables)}"
            )

            return chunks

        except (InvalidChunkingStrategyError, ChunkingError):
            raise

        except Exception as e:
            logger.error(
                f"Chonkie chunking failed: file_id={file_id}, error={str(e)}",
                exc_info=True,
            )
            raise ChunkingError(
                message=f"Failed to chunk text with Chonkie: {str(e)}",
                file_id=file_id,
                strategy=strategy.strategy_name.value,
            ) from e

    def get_supported_strategies(self) -> list[ChunkingStrategyName]:
        return list(self._supported_strategies)

    def _chunk_with_strategy(
        self, text: str, strategy: ChunkingStrategy
    ) -> list:
        """Route to the appropriate Chonkie chunker based on strategy."""
        if not text.strip():
            return []

        if strategy.strategy_name == ChunkingStrategyName.FIXED_SIZE:
            return self._chunk_fixed_size(text, strategy)

        if strategy.strategy_name == ChunkingStrategyName.MARKDOWN_AWARE:
            return self._chunk_markdown_aware(text, strategy)

        if strategy.strategy_name == ChunkingStrategyName.RECURSIVE:
            return self._chunk_recursive(text, strategy)

        if strategy.strategy_name == ChunkingStrategyName.SEMANTIC:
            return self._chunk_semantic(text, strategy)

        raise InvalidChunkingStrategyError(
            strategy_name=strategy.strategy_name.value,
            supported_strategies=[s.value for s in self.get_supported_strategies()],
        )

    def _get_or_create_chunker(
        self, strategy_name: str, chunk_size: int, chunk_overlap: int, factory: callable
    ) -> TokenChunker | RecursiveChunker | SemanticChunker:
        """Get a cached chunker or create and cache a new one."""
        key = (strategy_name, chunk_size, chunk_overlap)
        if key not in self._chunker_cache:
            self._chunker_cache[key] = factory()
        return self._chunker_cache[key]

    def _chunk_fixed_size(self, text: str, strategy: ChunkingStrategy) -> list:
        """Chunk using TokenChunker for fixed-size token-based chunking."""
        tokenizer = self._tokenizer
        chunker = self._get_or_create_chunker(
            "fixed_size",
            strategy.chunk_size,
            strategy.chunk_overlap,
            lambda: TokenChunker(
                tokenizer=tokenizer,
                chunk_size=strategy.chunk_size,
                chunk_overlap=strategy.chunk_overlap,
            ),
        )
        return chunker.chunk(text)

    def _chunk_markdown_aware(self, text: str, strategy: ChunkingStrategy) -> list:
        """Chunk using RecursiveChunker with vendored markdown rules (no HuggingFace download)."""
        tokenizer = self._tokenizer
        chunker = self._get_or_create_chunker(
            "markdown_aware",
            strategy.chunk_size,
            strategy.chunk_overlap,
            lambda: RecursiveChunker(
                tokenizer=tokenizer,
                chunk_size=strategy.chunk_size,
                rules=_MARKDOWN_EN_RULES,
                min_characters_per_chunk=24,
            ),
        )
        return chunker.chunk(text)

    def _chunk_recursive(self, text: str, strategy: ChunkingStrategy) -> list:
        """Chunk using RecursiveChunker with default recursive rules."""
        tokenizer = self._tokenizer
        chunker = self._get_or_create_chunker(
            "recursive",
            strategy.chunk_size,
            strategy.chunk_overlap,
            lambda: RecursiveChunker(
                tokenizer=tokenizer,
                chunk_size=strategy.chunk_size,
                min_characters_per_chunk=24,
            ),
        )
        return chunker.chunk(text)

    def _chunk_semantic(self, text: str, strategy: ChunkingStrategy) -> list:
        """Chunk using SemanticChunker for embedding-based boundary detection."""
        chunker = self._get_or_create_chunker(
            "semantic",
            strategy.chunk_size,
            strategy.chunk_overlap,
            lambda: SemanticChunker(
                embedding_model="minishlab/potion-base-32M",
                threshold=0.8,
                chunk_size=strategy.chunk_size,
                similarity_window=3,
            ),
        )
        return chunker.chunk(text)

    def _build_chunks(
        self,
        raw_chunks: list,
        tables: list[TableBlock],
        text_without_tables: str,
        original_text: str,
        file_id: str,
        strategy: ChunkingStrategy,
        heading_tracker: HeadingTracker,
        page_tracker: PageTracker,
    ) -> list[Chunk]:
        """Build final Chunk entities from raw chonkie chunks and extracted tables.

        Interleaves text chunks and table chunks in document order.
        """
        placeholder_pattern = get_placeholder_pattern()
        tables_by_placeholder_idx = {int(t.table_id.split("_")[1]): t for t in tables}

        # Collect all chunk items with their approximate position in original text
        chunk_items: list[tuple[int, Chunk]] = []
        chunk_counter = 0

        for raw_chunk in raw_chunks:
            chunk_text: str = raw_chunk.text
            chunk_start: int = raw_chunk.start_index
            chunk_end: int = raw_chunk.end_index

            # Check if this chunk contains a table placeholder
            placeholder_match = placeholder_pattern.search(chunk_text)

            if placeholder_match:
                # This chunk contains one or more table placeholders.
                # Split on placeholders and create separate chunks.
                parts = placeholder_pattern.split(chunk_text)

                for part_idx, part in enumerate(parts):
                    if part_idx % 2 == 0:
                        # Text part
                        stripped = part.strip()
                        if stripped:
                            # Map position back to original text approximately
                            original_offset = self._approximate_original_offset(
                                chunk_start, text_without_tables, original_text, tables
                            )
                            section_path = heading_tracker.section_path_at(original_offset)
                            token_count = count_tokens(stripped)

                            chunk_items.append((
                                original_offset,
                                Chunk(
                                    file_id=file_id,
                                    chunk_id=f"{file_id}_chunk_{chunk_counter}",
                                    chunk_index=chunk_counter,
                                    text=stripped,
                                    start_char=original_offset,
                                    end_char=original_offset + len(stripped),
                                    page_number=page_tracker.page_at(original_offset),
                                    metadata=ChunkMetadata(
                                        chunking_strategy=strategy.strategy_name.value,
                                        chunk_size=strategy.chunk_size,
                                        overlap_chars=strategy.chunk_overlap,
                                        token_count=token_count,
                                        section_path=section_path,
                                        has_table=False,
                                        page_label=page_tracker.page_label_at(original_offset),
                                        created_at=datetime.now(timezone.utc),
                                    ),
                                ),
                            ))
                            chunk_counter += 1
                    else:
                        # This is a captured group — the table placeholder index
                        table_idx = int(part)
                        table = tables_by_placeholder_idx.get(table_idx)
                        if table:
                            section_path = heading_tracker.section_path_at(table.start_index)
                            token_count = count_tokens(table.html)

                            chunk_items.append((
                                table.start_index,
                                Chunk(
                                    file_id=file_id,
                                    chunk_id=f"{file_id}_chunk_{chunk_counter}",
                                    chunk_index=chunk_counter,
                                    text=table.html,
                                    start_char=table.start_index,
                                    end_char=table.end_index,
                                    page_number=page_tracker.page_at(table.start_index),
                                    metadata=ChunkMetadata(
                                        chunking_strategy=strategy.strategy_name.value,
                                        chunk_size=strategy.chunk_size,
                                        overlap_chars=strategy.chunk_overlap,
                                        token_count=token_count,
                                        section_path=section_path,
                                        has_table=True,
                                        table_id=table.table_id,
                                        page_label=page_tracker.page_label_at(table.start_index),
                                        created_at=datetime.now(timezone.utc),
                                    ),
                                ),
                            ))
                            chunk_counter += 1
            else:
                # Pure text chunk — no placeholders
                original_offset = self._approximate_original_offset(
                    chunk_start, text_without_tables, original_text, tables
                )
                section_path = heading_tracker.section_path_at(original_offset)
                token_count = count_tokens(chunk_text)

                chunk_items.append((
                    original_offset,
                    Chunk(
                        file_id=file_id,
                        chunk_id=f"{file_id}_chunk_{chunk_counter}",
                        chunk_index=chunk_counter,
                        text=chunk_text,
                        start_char=original_offset,
                        end_char=original_offset + len(chunk_text),
                        page_number=page_tracker.page_at(original_offset),
                        metadata=ChunkMetadata(
                            chunking_strategy=strategy.strategy_name.value,
                            chunk_size=strategy.chunk_size,
                            overlap_chars=strategy.chunk_overlap,
                            token_count=token_count,
                            section_path=section_path,
                            has_table=False,
                            page_label=page_tracker.page_label_at(original_offset),
                            created_at=datetime.now(timezone.utc),
                        ),
                    ),
                ))
                chunk_counter += 1

        # Also add table chunks that may not have appeared in any text chunk's placeholder
        # (e.g., if the text around them was empty and the chunker dropped them)
        added_table_ids = {
            c.metadata.table_id for _, c in chunk_items if c.metadata.table_id
        }
        for table in tables:
            if table.table_id not in added_table_ids:
                section_path = heading_tracker.section_path_at(table.start_index)
                token_count = count_tokens(table.html)

                chunk_items.append((
                    table.start_index,
                    Chunk(
                        file_id=file_id,
                        chunk_id=f"{file_id}_chunk_{chunk_counter}",
                        chunk_index=chunk_counter,
                        text=table.html,
                        start_char=table.start_index,
                        end_char=table.end_index,
                        page_number=page_tracker.page_at(table.start_index),
                        metadata=ChunkMetadata(
                            chunking_strategy=strategy.strategy_name.value,
                            chunk_size=strategy.chunk_size,
                            overlap_chars=strategy.chunk_overlap,
                            token_count=token_count,
                            section_path=section_path,
                            has_table=True,
                            table_id=table.table_id,
                            page_label=page_tracker.page_label_at(table.start_index),
                            created_at=datetime.now(timezone.utc),
                        ),
                    ),
                ))
                chunk_counter += 1

        # Sort by position in original document
        chunk_items.sort(key=lambda x: x[0])

        # Reassign chunk_index after sorting
        final_chunks = []
        for idx, (_, chunk) in enumerate(chunk_items):
            chunk.chunk_index = idx
            chunk.chunk_id = f"{file_id}_chunk_{idx}"
            final_chunks.append(chunk)

        return final_chunks

    def _approximate_original_offset(
        self,
        modified_offset: int,
        text_without_tables: str,
        original_text: str,
        tables: list[TableBlock],
    ) -> int:
        """Map an offset in the modified text (with placeholders) back to original text.

        For each table that was replaced before this offset, add back the difference
        between the original table HTML length and its placeholder length.
        """
        offset = modified_offset
        for table in tables:
            placeholder_len = len(table.placeholder)
            original_len = table.end_index - table.start_index

            # Find where the placeholder is in the modified text
            placeholder_pos = text_without_tables.find(table.placeholder)
            if placeholder_pos >= 0 and placeholder_pos < modified_offset:
                offset += original_len - placeholder_len

        return min(offset, len(original_text))
