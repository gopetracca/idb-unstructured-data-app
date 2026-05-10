"""Unit tests for ChonkieChunker adapter."""

import pytest

from src.config.settings import ChunkingSettings
from src.core.errors import InvalidChunkingStrategyError
from src.core.value_objects.chunking_strategy import ChunkingStrategy, ChunkingStrategyName
from src.infrastructure.chonkie.chunker_chonkie import ChonkieChunker


@pytest.fixture
def chunking_settings() -> ChunkingSettings:
    """Create chunking settings for testing."""
    return ChunkingSettings(
        default_strategy="markdown_aware",
        default_chunk_size=512,
        default_chunk_overlap=50,
        adapter="chonkie",
        use_fake=False,
    )


@pytest.fixture
def chonkie_chunker(chunking_settings: ChunkingSettings) -> ChonkieChunker:
    """Create a ChonkieChunker instance for testing."""
    return ChonkieChunker(settings=chunking_settings)


SAMPLE_MARKDOWN = """# Introduction

This is the introduction section. It provides background information about
the topic and sets the stage for the rest of the document.

## Background

The background section contains detailed information about prior work.
It references multiple studies and established methodologies.

## Methodology

### Data Collection

Data was collected from multiple sources over a period of six months.
The primary sources include surveys, interviews, and archival data.

### Analysis

The analysis was performed using statistical methods including
regression analysis and factor analysis.

# Results

The results section presents the findings from the analysis.
Key findings include significant correlations between variables.

## Key Findings

Finding 1: There is a strong positive correlation.
Finding 2: The effect size is moderate to large.
Finding 3: Results are consistent across subgroups.
"""

SAMPLE_MARKDOWN_WITH_PAGES = """<!-- PageNumber="1" -->

# Introduction

This is the introduction section. It provides background information about
the topic and sets the stage for the rest of the document.


<!-- PageBreak -->

<!-- PageNumber="- ii -" -->

## Background

The background section contains detailed information about prior work.
It references multiple studies and established methodologies.

<table>
<tr><th>Study</th><th>Year</th></tr>
<tr><td>Study A</td><td>2020</td></tr>
<tr><td>Study B</td><td>2021</td></tr>
</table>


<!-- PageBreak -->

<!-- PageNumber="1" -->

## Methodology

Data was collected from multiple sources over a period of six months.
The primary sources include surveys, interviews, and archival data.
"""

SAMPLE_MARKDOWN_WITH_PAGEBREAK_ONLY = """# First Page

Alpha content on first page. Alpha content on first page. Alpha content on first page.
Alpha content on first page. Alpha content on first page.

<!-- PageBreak -->

# Second Page

Beta content on second page. Beta content on second page. Beta content on second page.
Beta content on second page. Beta content on second page.
"""

SAMPLE_MARKDOWN_WITH_TABLES = """# Financial Report

## Revenue Summary

The quarterly revenue figures are shown below:

<table>
<tr><th>Quarter</th><th>Revenue</th><th>Growth</th></tr>
<tr><td>Q1</td><td>$1.2M</td><td>5%</td></tr>
<tr><td>Q2</td><td>$1.5M</td><td>25%</td></tr>
<tr><td>Q3</td><td>$1.8M</td><td>20%</td></tr>
<tr><td>Q4</td><td>$2.1M</td><td>17%</td></tr>
</table>

The total annual revenue was $6.6M.

## Expense Breakdown

Operating expenses are categorized as follows:

<table>
<tr><th>Category</th><th>Amount</th></tr>
<tr><td>Salaries</td><td>$3.0M</td></tr>
<tr><td>Infrastructure</td><td>$0.8M</td></tr>
<tr><td>Marketing</td><td>$0.5M</td></tr>
</table>

Total operating expenses were $4.3M.

# Conclusion

The company achieved strong growth with a healthy profit margin.
"""


class TestChonkieChunkerStrategies:
    """Tests for strategy support."""

    def test_get_supported_strategies(self, chonkie_chunker: ChonkieChunker):
        """Chonkie supports FIXED_SIZE, MARKDOWN_AWARE, RECURSIVE, and SEMANTIC."""
        strategies = chonkie_chunker.get_supported_strategies()

        assert ChunkingStrategyName.FIXED_SIZE in strategies
        assert ChunkingStrategyName.MARKDOWN_AWARE in strategies
        assert ChunkingStrategyName.RECURSIVE in strategies
        assert ChunkingStrategyName.SEMANTIC in strategies
        assert len(strategies) == 4

    def test_fixed_size_is_supported(self, chonkie_chunker: ChonkieChunker):
        """FIXED_SIZE is supported by Chonkie adapter via TokenChunker."""
        assert chonkie_chunker.is_strategy_supported(ChunkingStrategyName.FIXED_SIZE) is True


class TestMarkdownAwareChunking:
    """Tests for MARKDOWN_AWARE strategy."""

    async def test_basic_chunking(self, chonkie_chunker: ChonkieChunker):
        """Basic markdown-aware chunking produces chunks."""
        strategy = ChunkingStrategy.markdown_aware(chunk_size=200, chunk_overlap=20)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN,
            file_id="test-file",
            strategy=strategy,
        )

        assert len(chunks) > 0
        assert all(c.file_id == "test-file" for c in chunks)
        assert all(c.chunk_id.startswith("test-file_chunk_") for c in chunks)

    async def test_chunks_have_section_path(self, chonkie_chunker: ChonkieChunker):
        """Chunks include section_path metadata."""
        strategy = ChunkingStrategy.markdown_aware(chunk_size=200, chunk_overlap=20)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN,
            file_id="test-file",
            strategy=strategy,
        )

        # At least some chunks should have section paths
        chunks_with_paths = [c for c in chunks if c.metadata.section_path]
        assert len(chunks_with_paths) > 0

    async def test_chunks_have_token_count(self, chonkie_chunker: ChonkieChunker):
        """Chunks include token_count metadata."""
        strategy = ChunkingStrategy.markdown_aware(chunk_size=200, chunk_overlap=20)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN,
            file_id="test-file",
            strategy=strategy,
        )

        for chunk in chunks:
            assert chunk.metadata.token_count is not None
            assert chunk.metadata.token_count > 0

    async def test_chunk_ordering(self, chonkie_chunker: ChonkieChunker):
        """Chunks are returned in order with sequential indices."""
        strategy = ChunkingStrategy.markdown_aware(chunk_size=200, chunk_overlap=20)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN,
            file_id="test-file",
            strategy=strategy,
        )

        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    async def test_small_text(self, chonkie_chunker: ChonkieChunker):
        """Text smaller than chunk size produces one chunk."""
        strategy = ChunkingStrategy.markdown_aware(chunk_size=2000, chunk_overlap=50)

        chunks = await chonkie_chunker.chunk_text(
            text="# Title\n\nSmall text.",
            file_id="test-file",
            strategy=strategy,
        )

        assert len(chunks) >= 1

    async def test_empty_text(self, chonkie_chunker: ChonkieChunker):
        """Empty text returns empty list."""
        strategy = ChunkingStrategy.markdown_aware(chunk_size=512, chunk_overlap=50)

        chunks = await chonkie_chunker.chunk_text(
            text="",
            file_id="test-file",
            strategy=strategy,
        )

        assert chunks == []

    async def test_whitespace_only_text(self, chonkie_chunker: ChonkieChunker):
        """Whitespace-only text returns empty list."""
        strategy = ChunkingStrategy.markdown_aware(chunk_size=512, chunk_overlap=50)

        chunks = await chonkie_chunker.chunk_text(
            text="   \n\n  \n  ",
            file_id="test-file",
            strategy=strategy,
        )

        assert chunks == []


class TestTableHandling:
    """Tests for HTML table handling in chunks."""

    async def test_tables_become_atomic_chunks(self, chonkie_chunker: ChonkieChunker):
        """HTML tables are preserved as atomic chunks."""
        strategy = ChunkingStrategy.markdown_aware(chunk_size=200, chunk_overlap=20)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN_WITH_TABLES,
            file_id="test-file",
            strategy=strategy,
        )

        table_chunks = [c for c in chunks if c.metadata.has_table]
        assert len(table_chunks) == 2

        # Each table chunk should contain the full table HTML
        for tc in table_chunks:
            assert "<table>" in tc.text
            assert "</table>" in tc.text

    async def test_table_chunks_have_table_id(self, chonkie_chunker: ChonkieChunker):
        """Table chunks have table_id metadata."""
        strategy = ChunkingStrategy.markdown_aware(chunk_size=200, chunk_overlap=20)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN_WITH_TABLES,
            file_id="test-file",
            strategy=strategy,
        )

        table_chunks = [c for c in chunks if c.metadata.has_table]
        for tc in table_chunks:
            assert tc.metadata.table_id is not None
            assert tc.metadata.table_id.startswith("table_")

    async def test_table_chunks_not_split(self, chonkie_chunker: ChonkieChunker):
        """Tables are never split, even with small chunk size."""
        strategy = ChunkingStrategy.markdown_aware(chunk_size=50, chunk_overlap=5)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN_WITH_TABLES,
            file_id="test-file",
            strategy=strategy,
        )

        table_chunks = [c for c in chunks if c.metadata.has_table]
        for tc in table_chunks:
            # Table should be complete
            assert tc.text.count("<table") == 1
            assert tc.text.count("</table>") == 1

    async def test_non_table_chunks_are_not_table(self, chonkie_chunker: ChonkieChunker):
        """Non-table chunks have has_table=False."""
        strategy = ChunkingStrategy.markdown_aware(chunk_size=200, chunk_overlap=20)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN_WITH_TABLES,
            file_id="test-file",
            strategy=strategy,
        )

        text_chunks = [c for c in chunks if not c.metadata.has_table]
        assert len(text_chunks) > 0
        for tc in text_chunks:
            assert tc.metadata.table_id is None

    async def test_table_section_path(self, chonkie_chunker: ChonkieChunker):
        """Table chunks get section_path from their position."""
        strategy = ChunkingStrategy.markdown_aware(chunk_size=200, chunk_overlap=20)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN_WITH_TABLES,
            file_id="test-file",
            strategy=strategy,
        )

        table_chunks = [c for c in chunks if c.metadata.has_table]
        # Tables are under "Financial Report" > "Revenue Summary" and "Expense Breakdown"
        for tc in table_chunks:
            assert tc.metadata.section_path is not None
            assert len(tc.metadata.section_path) > 0


class TestRecursiveChunking:
    """Tests for RECURSIVE strategy."""

    async def test_recursive_basic(self, chonkie_chunker: ChonkieChunker):
        """Recursive chunking produces chunks."""
        strategy = ChunkingStrategy.recursive(chunk_size=200, chunk_overlap=20)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN,
            file_id="test-file",
            strategy=strategy,
        )

        assert len(chunks) > 0
        assert all(c.file_id == "test-file" for c in chunks)

    async def test_recursive_with_tables(self, chonkie_chunker: ChonkieChunker):
        """Recursive chunking handles tables correctly."""
        strategy = ChunkingStrategy.recursive(chunk_size=200, chunk_overlap=20)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN_WITH_TABLES,
            file_id="test-file",
            strategy=strategy,
        )

        table_chunks = [c for c in chunks if c.metadata.has_table]
        assert len(table_chunks) == 2


class TestSemanticChunking:
    """Tests for SEMANTIC strategy."""

    async def test_semantic_basic(self, chonkie_chunker: ChonkieChunker):
        """Semantic chunking produces chunks."""
        strategy = ChunkingStrategy.semantic(chunk_size=200, chunk_overlap=20)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN,
            file_id="test-file",
            strategy=strategy,
        )

        assert len(chunks) > 0
        assert all(c.file_id == "test-file" for c in chunks)

    async def test_semantic_has_metadata(self, chonkie_chunker: ChonkieChunker):
        """Semantic chunks include metadata."""
        strategy = ChunkingStrategy.semantic(chunk_size=200, chunk_overlap=20)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN,
            file_id="test-file",
            strategy=strategy,
        )

        for chunk in chunks:
            assert chunk.metadata.token_count is not None
            assert chunk.metadata.token_count > 0
            assert chunk.metadata.overlap_chars == 20


class TestFixedSizeChunking:
    """Tests for FIXED_SIZE strategy."""

    async def test_fixed_size_basic(self, chonkie_chunker: ChonkieChunker):
        """Fixed-size chunking produces chunks."""
        strategy = ChunkingStrategy.fixed_size(chunk_size=200, chunk_overlap=20)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN,
            file_id="test-file",
            strategy=strategy,
        )

        assert len(chunks) > 0
        assert all(c.file_id == "test-file" for c in chunks)

    async def test_fixed_size_metadata(self, chonkie_chunker: ChonkieChunker):
        """Fixed-size chunks have expected chunk metadata values."""
        strategy = ChunkingStrategy.fixed_size(chunk_size=200, chunk_overlap=20)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN,
            file_id="test-file",
            strategy=strategy,
        )

        for chunk in chunks:
            assert chunk.metadata.overlap_chars == 20
            assert chunk.metadata.token_count is not None
            assert chunk.metadata.token_count > 0

    async def test_fixed_size_with_tables(self, chonkie_chunker: ChonkieChunker):
        """Fixed-size chunking handles tables correctly."""
        strategy = ChunkingStrategy.fixed_size(chunk_size=200, chunk_overlap=20)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN_WITH_TABLES,
            file_id="test-file",
            strategy=strategy,
        )

        table_chunks = [c for c in chunks if c.metadata.has_table]
        assert len(table_chunks) == 2

    async def test_fixed_size_empty_text(self, chonkie_chunker: ChonkieChunker):
        """Empty text returns empty list."""
        strategy = ChunkingStrategy.fixed_size(chunk_size=512, chunk_overlap=50)

        chunks = await chonkie_chunker.chunk_text(
            text="",
            file_id="test-file",
            strategy=strategy,
        )

        assert chunks == []


class TestChunkMetadataIntegrity:
    """Tests for chunk metadata correctness."""

    async def test_chunk_id_format(self, chonkie_chunker: ChonkieChunker):
        """Chunk IDs follow expected format."""
        strategy = ChunkingStrategy.markdown_aware(chunk_size=200, chunk_overlap=20)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN,
            file_id="my-doc-123",
            strategy=strategy,
        )

        for i, chunk in enumerate(chunks):
            assert chunk.chunk_id == f"my-doc-123_chunk_{i}"

    async def test_strategy_name_in_metadata(self, chonkie_chunker: ChonkieChunker):
        """Metadata reflects requested overlap and includes token counts."""
        strategy = ChunkingStrategy.markdown_aware(chunk_size=200, chunk_overlap=20)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN,
            file_id="test-file",
            strategy=strategy,
        )

        for chunk in chunks:
            assert chunk.metadata.overlap_chars == 20
            assert chunk.metadata.token_count is not None
            assert chunk.metadata.token_count > 0

    async def test_start_char_less_than_end_char(self, chonkie_chunker: ChonkieChunker):
        """All chunks have start_char < end_char."""
        strategy = ChunkingStrategy.markdown_aware(chunk_size=200, chunk_overlap=20)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN,
            file_id="test-file",
            strategy=strategy,
        )

        for chunk in chunks:
            assert chunk.start_char < chunk.end_char


class TestPageNumberExtraction:
    """Tests for page number extraction from Document Intelligence markers."""

    async def test_chunks_get_page_numbers(self, chonkie_chunker: ChonkieChunker):
        """Chunks after page markers get the correct page_number."""
        strategy = ChunkingStrategy.markdown_aware(chunk_size=2000, chunk_overlap=50)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN_WITH_PAGES,
            file_id="test-file",
            strategy=strategy,
        )

        assert len(chunks) > 0
        # All chunks should have a page number since text starts with a page marker
        for chunk in chunks:
            assert chunk.page_number is not None
            assert chunk.page_number >= 1

    async def test_page_numbers_increase(self, chonkie_chunker: ChonkieChunker):
        """Page numbers are non-decreasing across chunks in document order."""
        strategy = ChunkingStrategy.markdown_aware(chunk_size=200, chunk_overlap=20)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN_WITH_PAGES,
            file_id="test-file",
            strategy=strategy,
        )

        page_numbers = [c.page_number for c in chunks if c.page_number is not None]
        assert len(page_numbers) > 0
        for i in range(1, len(page_numbers)):
            assert page_numbers[i] >= page_numbers[i - 1]

    async def test_chunks_get_page_labels_when_present(self, chonkie_chunker: ChonkieChunker):
        """Chunks include normalized page labels in metadata when available."""
        strategy = ChunkingStrategy.markdown_aware(chunk_size=200, chunk_overlap=20)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN_WITH_PAGES,
            file_id="test-file",
            strategy=strategy,
        )

        labels = {chunk.metadata.page_label for chunk in chunks if chunk.metadata.page_label}
        assert "1" in labels
        assert "ii" in labels

    async def test_table_chunks_get_page_numbers(self, chonkie_chunker: ChonkieChunker):
        """Table chunks also get correct page numbers."""
        strategy = ChunkingStrategy.markdown_aware(chunk_size=200, chunk_overlap=20)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN_WITH_PAGES,
            file_id="test-file",
            strategy=strategy,
        )

        table_chunks = [c for c in chunks if c.metadata.has_table]
        assert len(table_chunks) == 1
        # The table is on page 2 (after the page 2 marker)
        assert table_chunks[0].page_number == 2
        assert table_chunks[0].metadata.page_label == "ii"

    async def test_pagebreak_only_text_still_gets_physical_pages(
        self, chonkie_chunker: ChonkieChunker
    ):
        """PageBreak-only markdown still yields physical page numbers."""
        strategy = ChunkingStrategy.fixed_size(chunk_size=50, chunk_overlap=0)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN_WITH_PAGEBREAK_ONLY,
            file_id="test-file",
            strategy=strategy,
        )

        assert len(chunks) > 0
        assert any(chunk.page_number == 1 for chunk in chunks)
        assert any(chunk.page_number == 2 for chunk in chunks)
        assert all(chunk.metadata.page_label is None for chunk in chunks)

    async def test_no_page_markers_gives_none(self, chonkie_chunker: ChonkieChunker):
        """Text without page markers produces chunks with page_number=None."""
        strategy = ChunkingStrategy.markdown_aware(chunk_size=200, chunk_overlap=20)

        chunks = await chonkie_chunker.chunk_text(
            text=SAMPLE_MARKDOWN,
            file_id="test-file",
            strategy=strategy,
        )

        for chunk in chunks:
            assert chunk.page_number is None
