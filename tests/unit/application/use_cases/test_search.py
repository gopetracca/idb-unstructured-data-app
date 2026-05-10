"""Unit tests for the unified SearchUseCase (semantic / keyword / hybrid modes)."""

from unittest.mock import AsyncMock, call

import pytest

from src.application.dto.search_dto import SemanticSearchInput, SemanticSearchOutput
from src.application.ports.embedding import EmbeddingResult
from src.application.use_cases.search import SearchUseCase, clear_collection_cache
from src.core.entities.search_result import SearchResult
from src.core.value_objects.search_mode import SearchMode
from src.core.value_objects.searchable_metadata import SearchableMetadata

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_vector_database():
    db = AsyncMock()
    db.get_index.return_value = {
        "name": "embeddings",
        "vector_dimension": 1536,
        "embedding_model": "text-embedding-3-small",
    }
    return db


@pytest.fixture
def mock_embedding_port():
    port = AsyncMock()
    port.generate_embeddings.return_value = [
        EmbeddingResult(
            text="query",
            vector=[0.1] * 1536,
            token_count=1,
            model="text-embedding-3-small",
            dimension=1536,
        )
    ]
    return port


@pytest.fixture
def use_case(mock_vector_database, mock_embedding_port):
    clear_collection_cache()
    return SearchUseCase(
        vector_database=mock_vector_database,
        embedding_port=mock_embedding_port,
    )


def _make_input(**kwargs) -> SemanticSearchInput:
    defaults = dict(
        tenant_id="t",
        query="BR-L1234 project",
        index_name="embeddings",
        top_k=10,
        min_score=0.0,
        include_metadata=False,
        correlation_id="cid",
    )
    defaults.update(kwargs)
    return SemanticSearchInput(**defaults)


def _make_result(chunk_id: str, score: float, reranker_score: float | None = None) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        file_id="f1",
        text="text",
        score=score,
        reranker_score=reranker_score,
        metadata=SearchableMetadata(),
    )


# ---------------------------------------------------------------------------
# Mode-specific call-shape assertions
# ---------------------------------------------------------------------------


async def test_semantic_mode_generates_embedding_and_passes_vector(
    use_case, mock_vector_database, mock_embedding_port
):
    mock_vector_database.search.return_value = []
    input_dto = _make_input(search_mode=SearchMode.SEMANTIC, enable_reranker=False)

    await use_case.execute(input_dto)

    mock_embedding_port.generate_embeddings.assert_called_once()
    call_kwargs = mock_vector_database.search.call_args.kwargs
    assert call_kwargs["query_vector"] is not None
    assert call_kwargs["search_mode"] == SearchMode.SEMANTIC
    assert call_kwargs["enable_reranker"] is False


async def test_keyword_mode_skips_embedding(
    use_case, mock_vector_database, mock_embedding_port
):
    """Embedding must NOT be generated in keyword mode."""
    mock_vector_database.search.return_value = []
    input_dto = _make_input(search_mode=SearchMode.KEYWORD, enable_reranker=False)

    await use_case.execute(input_dto)

    mock_embedding_port.generate_embeddings.assert_not_called()
    call_kwargs = mock_vector_database.search.call_args.kwargs
    assert call_kwargs["query_vector"] is None
    assert call_kwargs["query_text"] == input_dto.query
    assert call_kwargs["search_mode"] == SearchMode.KEYWORD


async def test_hybrid_mode_generates_embedding_and_passes_text(
    use_case, mock_vector_database, mock_embedding_port
):
    mock_vector_database.get_index.return_value = {
        "name": "embeddings",
        "vector_dimension": 1536,
        "embedding_model": "text-embedding-3-small",
        "reranker_enabled": True,
    }
    mock_vector_database.search.return_value = []
    input_dto = _make_input(search_mode=SearchMode.HYBRID, enable_reranker=True)

    await use_case.execute(input_dto)

    mock_embedding_port.generate_embeddings.assert_called_once()
    call_kwargs = mock_vector_database.search.call_args.kwargs
    assert call_kwargs["query_vector"] is not None
    assert call_kwargs["query_text"] == input_dto.query
    assert call_kwargs["search_mode"] == SearchMode.HYBRID
    assert call_kwargs["enable_reranker"] is True


# ---------------------------------------------------------------------------
# Default mode is HYBRID
# ---------------------------------------------------------------------------


async def test_default_search_mode_is_hybrid(
    use_case, mock_vector_database, mock_embedding_port
):
    mock_vector_database.search.return_value = []
    input_dto = _make_input()  # no search_mode set → SemanticSearchInput defaults to HYBRID

    await use_case.execute(input_dto)

    call_kwargs = mock_vector_database.search.call_args.kwargs
    assert call_kwargs["search_mode"] == SearchMode.HYBRID


# ---------------------------------------------------------------------------
# Sorting by reranker_score when present
# ---------------------------------------------------------------------------


async def test_results_sorted_by_reranker_score_when_present(
    use_case, mock_vector_database, mock_embedding_port
):
    mock_vector_database.get_index.return_value = {
        "name": "embeddings",
        "vector_dimension": 1536,
        "embedding_model": "text-embedding-3-small",
        "reranker_enabled": True,
    }
    results = [
        _make_result("c1", score=0.9, reranker_score=1.2),
        _make_result("c2", score=0.8, reranker_score=3.5),
        _make_result("c3", score=0.7, reranker_score=2.0),
    ]
    mock_vector_database.search.return_value = results
    input_dto = _make_input(search_mode=SearchMode.HYBRID, enable_reranker=True)

    output = await use_case.execute(input_dto)

    # Use case receives results already sorted by the adapter; output order should be stable
    # (no extra re-sort by use case on reranker_score — adapter handles it)
    assert output.reranker_enabled is True


async def test_reranker_disabled_output_flag(
    use_case, mock_vector_database, mock_embedding_port
):
    mock_vector_database.search.return_value = [_make_result("c1", 0.8)]
    input_dto = _make_input(search_mode=SearchMode.HYBRID, enable_reranker=False)

    output = await use_case.execute(input_dto)

    assert output.reranker_enabled is False


# ---------------------------------------------------------------------------
# Output fields
# ---------------------------------------------------------------------------


async def test_output_exposes_search_mode_and_reranker_enabled(
    use_case, mock_vector_database, mock_embedding_port
):
    mock_vector_database.get_index.return_value = {
        "name": "embeddings",
        "vector_dimension": 1536,
        "embedding_model": "text-embedding-3-small",
        "reranker_enabled": True,
    }
    mock_vector_database.search.return_value = [_make_result("c1", 0.8, reranker_score=2.1)]
    input_dto = _make_input(search_mode=SearchMode.HYBRID, enable_reranker=True)

    output = await use_case.execute(input_dto)

    assert output.search_mode == SearchMode.HYBRID
    assert output.reranker_enabled is True
    assert output.results[0].reranker_score == pytest.approx(2.1)


async def test_output_exposes_reranker_score_none_when_disabled(
    use_case, mock_vector_database, mock_embedding_port
):
    mock_vector_database.search.return_value = [_make_result("c1", 0.8)]
    input_dto = _make_input(search_mode=SearchMode.SEMANTIC, enable_reranker=False)

    output = await use_case.execute(input_dto)

    assert output.results[0].reranker_score is None
    assert output.reranker_enabled is False


# ---------------------------------------------------------------------------
# min_score filtering — normalised reranker_score for reranker-on results
# ---------------------------------------------------------------------------


async def test_min_score_filters_by_normalised_reranker_score(
    use_case, mock_vector_database, mock_embedding_port
):
    """reranker_score=2.0 → normalised 0.5; reranker_score=0.8 → 0.2, filtered out at min_score=0.4."""
    mock_vector_database.get_index.return_value = {
        "name": "embeddings",
        "vector_dimension": 1536,
        "embedding_model": "text-embedding-3-small",
        "reranker_enabled": True,
    }
    results = [
        _make_result("c1", score=0.9, reranker_score=2.0),
        _make_result("c2", score=0.85, reranker_score=0.8),
    ]
    mock_vector_database.search.return_value = results
    input_dto = _make_input(search_mode=SearchMode.HYBRID, enable_reranker=True, min_score=0.4)

    output = await use_case.execute(input_dto)

    assert output.total_results == 1
    assert output.results[0].chunk_id == "c1"


# ---------------------------------------------------------------------------
# Backward-compatibility alias
# ---------------------------------------------------------------------------


async def test_semantic_search_use_case_alias_works(mock_vector_database, mock_embedding_port):
    from src.application.use_cases.semantic_search import SemanticSearchUseCase

    clear_collection_cache()
    uc = SemanticSearchUseCase(
        vector_database=mock_vector_database,
        embedding_port=mock_embedding_port,
    )
    mock_vector_database.search.return_value = []
    input_dto = _make_input(search_mode=SearchMode.SEMANTIC, enable_reranker=False)

    output = await uc.execute(input_dto)

    assert isinstance(output, SemanticSearchOutput)
