"""Unit tests for SemanticSearchUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.application.dto.search_dto import SemanticSearchInput, SemanticSearchOutput
from src.application.ports.embedding import EmbeddingResult
from src.application.use_cases.semantic_search import (
    SemanticSearchUseCase,
    clear_collection_cache,
)
from src.core.entities.search_result import SearchResult
from src.core.errors import UnsupportedFilterError, ValidationError
from src.core.value_objects.searchable_metadata import SearchableMetadata


@pytest.fixture
def mock_vector_database():
    """Mock vector database port."""
    return AsyncMock()


@pytest.fixture
def mock_embedding_port():
    """Mock embedding port."""
    return AsyncMock()


@pytest.fixture
def semantic_search_use_case(mock_vector_database, mock_embedding_port):
    """Create SemanticSearchUseCase with mocked dependencies."""
    clear_collection_cache()
    return SemanticSearchUseCase(
        vector_database=mock_vector_database,
        embedding_port=mock_embedding_port,
    )


@pytest.fixture
def sample_search_input():
    """Create sample semantic search input."""
    return SemanticSearchInput(
        tenant_id="test-tenant",
        query="What is the company policy?",
        index_name="embeddings",
        top_k=10,
        min_score=0.0,
        file_ids=None,
        document_type=None,
        tags=None,
        department=None,
        source=None,
        include_metadata=False,
        correlation_id="test-correlation-id",
    )


@pytest.fixture
def sample_embedding_result():
    """Create sample embedding result."""
    return EmbeddingResult(
        text="What is the company policy?",
        vector=[0.1] * 1536,
        token_count=6,
        model="text-embedding-3-small",
        dimension=1536,
    )


@pytest.fixture
def sample_search_results():
    """Create sample search results."""
    return [
        SearchResult(
            chunk_id="file1#chunk-0",
            file_id="file1",
            text="The company policy states that employees can work remotely.",
            score=0.92,
            metadata=SearchableMetadata(page_number=1),
        ),
        SearchResult(
            chunk_id="file1#chunk-1",
            file_id="file1",
            text="Remote work must be approved by the manager.",
            score=0.85,
            metadata=SearchableMetadata(page_number=1),
        ),
        SearchResult(
            chunk_id="file2#chunk-0",
            file_id="file2",
            text="Employees are expected to follow company policies.",
            score=0.75,
            metadata=SearchableMetadata(page_number=2),
        ),
    ]


async def test_semantic_search_basic(
    semantic_search_use_case,
    mock_vector_database,
    mock_embedding_port,
    sample_search_input,
    sample_embedding_result,
    sample_search_results,
):
    """Test basic semantic search operation."""
    # Setup mocks
    mock_vector_database.get_index.return_value = {
        "name": "embeddings",
        "vector_dimension": 1536,
        "embedding_model": "text-embedding-3-small",
        "document_count": 100,
    }
    mock_embedding_port.generate_embeddings.return_value = [sample_embedding_result]
    mock_vector_database.search.return_value = sample_search_results

    # Execute
    output = await semantic_search_use_case.execute(sample_search_input)

    # Verify
    assert isinstance(output, SemanticSearchOutput)
    assert output.query == sample_search_input.query
    assert output.total_results == 3
    assert len(output.results) == 3
    assert output.results[0].score == 0.92
    assert output.embedding_model == "text-embedding-3-small"
    assert output.correlation_id == "test-correlation-id"

    # Verify collection info was fetched
    mock_vector_database.get_index.assert_called_once_with("embeddings")

    # Verify embedding was generated with collection's embedding model
    mock_embedding_port.generate_embeddings.assert_called_once_with(
        texts=["What is the company policy?"],
        model="text-embedding-3-small",
    )

    # Verify vector search was called
    mock_vector_database.search.assert_called_once()
    call_args = mock_vector_database.search.call_args
    assert call_args[1]["index_name"] == "embeddings"
    assert call_args[1]["query_vector"] == sample_embedding_result.vector
    assert call_args[1]["top_k"] == 10


async def test_semantic_search_with_filters(
    semantic_search_use_case,
    mock_vector_database,
    mock_embedding_port,
    sample_embedding_result,
    sample_search_results,
):
    """Test semantic search with metadata filters."""
    # Setup input with filters
    input_dto = SemanticSearchInput(
        tenant_id="test-tenant",
        query="remote work policy",
        index_name="embeddings",
        top_k=5,
        min_score=0.0,
        file_ids=["file1", "file2"],
        document_type="policy",
        tags=["hr", "remote"],
        department="hr",
        source="manual",
        include_metadata=False,
        correlation_id="test-id",
    )

    # Setup mocks
    mock_vector_database.get_index.return_value = {
        "name": "embeddings",
        "vector_dimension": 1536,
        "embedding_model": "text-embedding-3-small",
        "document_count": 100,
    }
    mock_embedding_port.generate_embeddings.return_value = [sample_embedding_result]
    mock_vector_database.search.return_value = sample_search_results

    # Execute
    output = await semantic_search_use_case.execute(input_dto)

    # Verify filters were built correctly
    call_args = mock_vector_database.search.call_args
    filters = call_args[1]["filters"]

    assert filters["file_ids"] == ["file1", "file2"]
    assert filters["document_type"] == "policy"
    assert filters["tags"] == ["hr", "remote"]
    assert filters["department"] == "hr"
    assert filters["source"] == "manual"

    # Verify filters are in output
    assert output.filters_applied == filters


async def test_semantic_search_min_score_filtering(
    semantic_search_use_case,
    mock_vector_database,
    mock_embedding_port,
    sample_search_input,
    sample_embedding_result,
    sample_search_results,
):
    """Test minimum score filtering."""
    # Set min_score to filter out low scores
    sample_search_input.min_score = 0.80

    # Setup mocks
    mock_vector_database.get_index.return_value = {
        "name": "embeddings",
        "vector_dimension": 1536,
        "embedding_model": "text-embedding-3-small",
        "document_count": 100,
    }
    mock_embedding_port.generate_embeddings.return_value = [sample_embedding_result]
    mock_vector_database.search.return_value = sample_search_results

    # Execute
    output = await semantic_search_use_case.execute(sample_search_input)

    # Verify only results with score >= 0.80 are returned
    assert output.total_results == 2
    assert all(result.score >= 0.80 for result in output.results)
    assert output.results[0].score == 0.92
    assert output.results[1].score == 0.85


async def test_semantic_search_empty_results(
    semantic_search_use_case,
    mock_vector_database,
    mock_embedding_port,
    sample_search_input,
    sample_embedding_result,
):
    """Test semantic search with no results."""
    # Setup mocks
    mock_vector_database.get_index.return_value = {
        "name": "embeddings",
        "vector_dimension": 1536,
        "embedding_model": "text-embedding-3-small",
        "document_count": 100,
    }
    mock_embedding_port.generate_embeddings.return_value = [sample_embedding_result]
    mock_vector_database.search.return_value = []

    # Execute
    output = await semantic_search_use_case.execute(sample_search_input)

    # Verify
    assert output.total_results == 0
    assert len(output.results) == 0


async def test_semantic_search_no_filters(
    semantic_search_use_case,
    mock_vector_database,
    mock_embedding_port,
    sample_search_input,
    sample_embedding_result,
    sample_search_results,
):
    """Test semantic search without any filters."""
    # Setup mocks
    mock_vector_database.get_index.return_value = {
        "name": "embeddings",
        "vector_dimension": 1536,
        "embedding_model": "text-embedding-3-small",
        "document_count": 100,
    }
    mock_embedding_port.generate_embeddings.return_value = [sample_embedding_result]
    mock_vector_database.search.return_value = sample_search_results

    # Execute
    output = await semantic_search_use_case.execute(sample_search_input)

    # Verify no filters were passed (None or empty dict)
    call_args = mock_vector_database.search.call_args
    filters = call_args[1]["filters"]
    assert filters is None or filters == {}
    assert output.filters_applied == {}


async def test_semantic_search_custom_index(
    semantic_search_use_case,
    mock_vector_database,
    mock_embedding_port,
    sample_search_input,
    sample_embedding_result,
    sample_search_results,
):
    """Test semantic search with custom index name."""
    # Set custom index
    sample_search_input.index_name = "custom-embeddings"

    # Setup mocks
    mock_vector_database.get_index.return_value = {
        "name": "custom-embeddings",
        "vector_dimension": 1536,
        "embedding_model": "text-embedding-3-small",
        "document_count": 50,
    }
    mock_embedding_port.generate_embeddings.return_value = [sample_embedding_result]
    mock_vector_database.search.return_value = sample_search_results

    # Execute
    output = await semantic_search_use_case.execute(sample_search_input)

    # Verify custom index was used
    call_args = mock_vector_database.search.call_args
    assert call_args[1]["index_name"] == "custom-embeddings"


async def test_semantic_search_performance_tracking(
    semantic_search_use_case,
    mock_vector_database,
    mock_embedding_port,
    sample_search_input,
    sample_embedding_result,
    sample_search_results,
):
    """Test that search time is tracked."""
    # Setup mocks
    mock_vector_database.get_index.return_value = {
        "name": "embeddings",
        "vector_dimension": 1536,
        "embedding_model": "text-embedding-3-small",
        "document_count": 100,
    }
    mock_embedding_port.generate_embeddings.return_value = [sample_embedding_result]
    mock_vector_database.search.return_value = sample_search_results

    # Execute
    output = await semantic_search_use_case.execute(sample_search_input)

    # Verify search time is tracked (may be 0 in mocked environment due to speed)
    assert output.search_time_ms >= 0
    assert isinstance(output.search_time_ms, int)


# ---------------------------------------------------------------------------
# Filter, sorting, and pagination behaviour — tested via execute()
# ---------------------------------------------------------------------------

def _make_index_info(name: str = "embeddings") -> dict:
    return {
        "name": name,
        "vector_dimension": 1536,
        "embedding_model": "text-embedding-3-small",
        "document_count": 100,
    }


def _make_embedding_result() -> EmbeddingResult:
    return EmbeddingResult(
        text="test", vector=[0.1] * 1536, token_count=1,
        model="text-embedding-3-small", dimension=1536,
    )


async def test_filters_file_ids_forwarded_to_vector_search(
    semantic_search_use_case, mock_vector_database, mock_embedding_port
):
    """File ID filters are forwarded to the vector database search call."""
    mock_vector_database.get_index.return_value = _make_index_info()
    mock_embedding_port.generate_embeddings.return_value = [_make_embedding_result()]
    mock_vector_database.search.return_value = []

    await semantic_search_use_case.execute(
        SemanticSearchInput(
            tenant_id="t", query="q", file_ids=["file1", "file2", "file3"],
            correlation_id="c",
        )
    )

    filters = mock_vector_database.search.call_args[1]["filters"]
    assert filters["file_ids"] == ["file1", "file2", "file3"]


async def test_filters_tags_forwarded_to_vector_search(
    semantic_search_use_case, mock_vector_database, mock_embedding_port
):
    """Tag filters are forwarded to the vector database search call."""
    mock_vector_database.get_index.return_value = _make_index_info()
    mock_embedding_port.generate_embeddings.return_value = [_make_embedding_result()]
    mock_vector_database.search.return_value = []

    await semantic_search_use_case.execute(
        SemanticSearchInput(tenant_id="t", query="q", tags=["tag1", "tag2"], correlation_id="c")
    )

    filters = mock_vector_database.search.call_args[1]["filters"]
    assert filters["tags"] == ["tag1", "tag2"]


async def test_filters_combined_forwarded_to_vector_search(
    semantic_search_use_case, mock_vector_database, mock_embedding_port
):
    """All supported filter fields are forwarded together."""
    mock_vector_database.get_index.return_value = _make_index_info()
    mock_embedding_port.generate_embeddings.return_value = [_make_embedding_result()]
    mock_vector_database.search.return_value = []

    await semantic_search_use_case.execute(
        SemanticSearchInput(
            tenant_id="t", query="q",
            file_ids=["file1"], document_type="policy",
            tags=["hr"], department="legal", source="manual",
            correlation_id="c",
        )
    )

    filters = mock_vector_database.search.call_args[1]["filters"]
    assert filters["file_ids"] == ["file1"]
    assert filters["document_type"] == "policy"
    assert filters["tags"] == ["hr"]
    assert filters["department"] == "legal"
    assert filters["source"] == "manual"


async def test_no_filters_passes_empty_to_vector_search(
    semantic_search_use_case, mock_vector_database, mock_embedding_port
):
    """When no filters are specified the search receives no filter constraints."""
    mock_vector_database.get_index.return_value = _make_index_info()
    mock_embedding_port.generate_embeddings.return_value = [_make_embedding_result()]
    mock_vector_database.search.return_value = []

    await semantic_search_use_case.execute(
        SemanticSearchInput(tenant_id="t", query="q", correlation_id="c")
    )

    filters = mock_vector_database.search.call_args[1]["filters"]
    assert not filters  # None or empty dict


async def test_unsupported_filter_raises_error(
    semantic_search_use_case, mock_vector_database, mock_embedding_port
):
    """An unrecognised filter key raises UnsupportedFilterError before search."""
    mock_vector_database.get_index.return_value = _make_index_info()
    mock_embedding_port.generate_embeddings.return_value = [_make_embedding_result()]

    with pytest.raises(UnsupportedFilterError):
        await semantic_search_use_case.execute(
            SemanticSearchInput(
                tenant_id="t", query="q",
                filters={"unsupported_key": "value"},
                correlation_id="c",
            )
        )

    mock_vector_database.search.assert_not_called()


async def test_pagination_beyond_limit_raises_error(
    semantic_search_use_case, mock_vector_database, mock_embedding_port
):
    """Requesting a page that would exceed the maximum result window raises ValidationError."""
    mock_vector_database.get_index.return_value = _make_index_info()
    mock_embedding_port.generate_embeddings.return_value = [_make_embedding_result()]

    with pytest.raises(ValidationError):
        await semantic_search_use_case.execute(
            SemanticSearchInput(
                tenant_id="t", query="q",
                page_size=50, page_number=3,
                correlation_id="c",
            )
        )


async def test_vector_dimension_mismatch_raises_validation_error(
    semantic_search_use_case, mock_vector_database, mock_embedding_port
):
    """A mismatch between index vector dimension and query embedding dimension is rejected."""
    mock_vector_database.get_index.return_value = {
        "name": "embeddings",
        "vector_dimension": 3,
        "embedding_model": "text-embedding-3-small",
        "document_count": 10,
    }
    mock_embedding_port.generate_embeddings.return_value = [
        EmbeddingResult(
            text="q",
            vector=[0.1] * 1536,
            token_count=1,
            model="text-embedding-3-small",
            dimension=1536,
        )
    ]

    with pytest.raises(ValidationError) as exc_info:
        await semantic_search_use_case.execute(
            SemanticSearchInput(tenant_id="t", query="q", correlation_id="c")
        )

    assert "dimension" in exc_info.value.message.lower()
    assert exc_info.value.details["expected_vector_dimension"] == 3
    assert exc_info.value.details["actual_query_vector_dimension"] == 1536
    mock_vector_database.search.assert_not_called()


def test_invalid_sort_field_rejected_at_dto_construction():
    """An unrecognised sort_by value is rejected by SemanticSearchInput validation."""
    from pydantic import ValidationError as PydanticValidationError

    with pytest.raises(PydanticValidationError):
        SemanticSearchInput(
            tenant_id="t", query="q", sort_by="unknown_field", correlation_id="c"
        )


async def test_results_sorted_by_score_descending(
    semantic_search_use_case, mock_vector_database, mock_embedding_port
):
    """Results are returned in descending score order when sort_by='score'."""
    mock_vector_database.get_index.return_value = _make_index_info()
    mock_embedding_port.generate_embeddings.return_value = [_make_embedding_result()]
    mock_vector_database.search.return_value = [
        SearchResult(chunk_id="low", file_id="f1", text="t", score=0.5, metadata=SearchableMetadata()),
        SearchResult(chunk_id="high", file_id="f2", text="t", score=0.9, metadata=SearchableMetadata()),
    ]

    output = await semantic_search_use_case.execute(
        SemanticSearchInput(
            tenant_id="t", query="q", sort_by="score", order="desc", correlation_id="c"
        )
    )

    assert [r.score for r in output.results] == [0.9, 0.5]


async def test_pagination_returns_correct_page(
    semantic_search_use_case, mock_vector_database, mock_embedding_port
):
    """Page 2 with page_size=2 returns the third and fourth results."""
    mock_vector_database.get_index.return_value = _make_index_info()
    mock_embedding_port.generate_embeddings.return_value = [_make_embedding_result()]
    mock_vector_database.search.return_value = [
        SearchResult(chunk_id=f"chunk-{i}", file_id="f", text="t", score=0.1 * i, metadata=SearchableMetadata())
        for i in range(1, 6)
    ]

    output = await semantic_search_use_case.execute(
        SemanticSearchInput(
            tenant_id="t", query="q", page_size=2, page_number=2, correlation_id="c"
        )
    )

    assert [r.chunk_id for r in output.results] == ["chunk-3", "chunk-4"]
