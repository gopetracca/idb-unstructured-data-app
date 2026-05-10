"""Unit tests for AzureAISearchAdapter search-mode branching and reranker logic."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.config.settings import VectorSearchSettings
from src.core.entities.search_result import SearchResult
from src.core.value_objects.search_mode import SearchMode
from src.infrastructure.azure.adapters.vector_search_azure import AzureAISearchAdapter


@pytest.fixture
def mock_settings():
    return VectorSearchSettings(
        endpoint="https://test.search.windows.net",
        api_key="test_key",
        default_index_name="test-index",
        semantic_configuration_name="default-semantic-config",
    )


@pytest.fixture
async def adapter(mock_settings):
    with patch("src.infrastructure.azure.adapters.vector_search_azure.SearchClientWrapper"):
        adapter = AzureAISearchAdapter(mock_settings)
        adapter._client_wrapper = AsyncMock()
        adapter._client_wrapper.index_client = AsyncMock()
        adapter._client_wrapper.get_search_client = Mock(return_value=AsyncMock())
        yield adapter


def _raw_result(chunk_id="c1", score=0.9, reranker_score=None):
    r = {
        "chunkId": chunk_id,
        "fileId": "f1",
        "content": "text",
        "@search.score": score,
        "metadata": {},
    }
    if reranker_score is not None:
        r["@search.reranker_score"] = reranker_score
    return r


async def _async_gen(*items):
    for item in items:
        yield item


class TestSearchModes:

    async def test_semantic_mode_sends_only_vector_query(self, adapter):
        mock_client = AsyncMock()
        mock_client.search = AsyncMock(return_value=_async_gen(_raw_result()))
        adapter._client_wrapper.get_search_client = Mock(return_value=mock_client)

        await adapter.search(
            "idx",
            query_text="query",
            query_vector=[0.1] * 1536,
            search_mode=SearchMode.SEMANTIC,
            enable_reranker=False,
        )

        call_kwargs = mock_client.search.call_args.kwargs
        assert call_kwargs["search_text"] is None
        assert call_kwargs["vector_queries"] is not None
        assert "query_type" not in call_kwargs

    async def test_keyword_mode_sends_only_search_text(self, adapter):
        mock_client = AsyncMock()
        mock_client.search = AsyncMock(return_value=_async_gen(_raw_result()))
        adapter._client_wrapper.get_search_client = Mock(return_value=mock_client)

        await adapter.search(
            "idx",
            query_text="BR-L1234",
            query_vector=None,
            search_mode=SearchMode.KEYWORD,
            enable_reranker=False,
        )

        call_kwargs = mock_client.search.call_args.kwargs
        assert call_kwargs["search_text"] == "BR-L1234"
        assert call_kwargs["vector_queries"] is None
        assert "query_type" not in call_kwargs

    async def test_hybrid_mode_sends_both_text_and_vector(self, adapter):
        mock_client = AsyncMock()
        mock_client.search = AsyncMock(return_value=_async_gen(_raw_result()))
        adapter._client_wrapper.get_search_client = Mock(return_value=mock_client)

        await adapter.search(
            "idx",
            query_text="hybrid query",
            query_vector=[0.1] * 1536,
            search_mode=SearchMode.HYBRID,
            enable_reranker=False,
        )

        call_kwargs = mock_client.search.call_args.kwargs
        assert call_kwargs["search_text"] == "hybrid query"
        assert call_kwargs["vector_queries"] is not None
        assert "query_type" not in call_kwargs

    async def test_reranker_on_hybrid_sets_query_type_semantic(self, adapter):
        mock_client = AsyncMock()
        mock_client.search = AsyncMock(return_value=_async_gen(_raw_result()))
        adapter._client_wrapper.get_search_client = Mock(return_value=mock_client)

        await adapter.search(
            "idx",
            query_text="query",
            query_vector=[0.1] * 1536,
            search_mode=SearchMode.HYBRID,
            enable_reranker=True,
        )

        call_kwargs = mock_client.search.call_args.kwargs
        assert call_kwargs.get("query_type") is not None
        assert call_kwargs.get("semantic_configuration_name") == "default-semantic-config"
        assert call_kwargs.get("query_caption") == "extractive"
        assert call_kwargs.get("query_answer") == "extractive"

    async def test_reranker_on_keyword_sets_query_type_semantic(self, adapter):
        mock_client = AsyncMock()
        mock_client.search = AsyncMock(return_value=_async_gen(_raw_result()))
        adapter._client_wrapper.get_search_client = Mock(return_value=mock_client)

        await adapter.search(
            "idx",
            query_text="query",
            query_vector=None,
            search_mode=SearchMode.KEYWORD,
            enable_reranker=True,
        )

        call_kwargs = mock_client.search.call_args.kwargs
        assert call_kwargs.get("query_type") is not None
        assert call_kwargs.get("semantic_configuration_name") == "default-semantic-config"

    async def test_reranker_uses_request_profile_when_provided(self, adapter):
        mock_client = AsyncMock()
        mock_client.search = AsyncMock(return_value=_async_gen(_raw_result()))
        adapter._client_wrapper.get_search_client = Mock(return_value=mock_client)

        await adapter.search(
            "idx",
            query_text="query",
            query_vector=None,
            search_mode=SearchMode.KEYWORD,
            enable_reranker=True,
            reranker_profile="custom-semantic-config",
        )

        call_kwargs = mock_client.search.call_args.kwargs
        assert call_kwargs.get("query_type") is not None
        assert call_kwargs.get("semantic_configuration_name") == "custom-semantic-config"

    async def test_reranker_NOT_applied_to_semantic_mode(self, adapter):
        """Even if enable_reranker=True, semantic (vector-only) mode must NOT set query_type."""
        mock_client = AsyncMock()
        mock_client.search = AsyncMock(return_value=_async_gen(_raw_result()))
        adapter._client_wrapper.get_search_client = Mock(return_value=mock_client)

        await adapter.search(
            "idx",
            query_text="query",
            query_vector=[0.1] * 1536,
            search_mode=SearchMode.SEMANTIC,
            enable_reranker=True,
        )

        call_kwargs = mock_client.search.call_args.kwargs
        assert "query_type" not in call_kwargs

    async def test_reranker_score_is_surfaced_in_results(self, adapter):
        mock_client = AsyncMock()
        mock_client.search = AsyncMock(
            return_value=_async_gen(_raw_result("c1", 0.9, reranker_score=3.2))
        )
        adapter._client_wrapper.get_search_client = Mock(return_value=mock_client)

        results = await adapter.search(
            "idx",
            query_text="q",
            query_vector=[0.1] * 1536,
            search_mode=SearchMode.HYBRID,
            enable_reranker=True,
        )

        assert len(results) == 1
        assert results[0].reranker_score == pytest.approx(3.2)

    async def test_results_sorted_by_reranker_score_desc(self, adapter):
        mock_client = AsyncMock()
        mock_client.search = AsyncMock(
            return_value=_async_gen(
                _raw_result("c1", 0.9, reranker_score=1.0),
                _raw_result("c2", 0.8, reranker_score=3.5),
                _raw_result("c3", 0.7, reranker_score=2.2),
            )
        )
        adapter._client_wrapper.get_search_client = Mock(return_value=mock_client)

        results = await adapter.search(
            "idx",
            query_text="q",
            query_vector=[0.1] * 1536,
            search_mode=SearchMode.HYBRID,
            enable_reranker=True,
        )

        scores = [r.reranker_score for r in results]
        assert scores == sorted(scores, reverse=True)

    async def test_no_reranker_sort_when_disabled(self, adapter):
        """When reranker is off, adapter returns results in Azure's original order."""
        mock_client = AsyncMock()
        mock_client.search = AsyncMock(
            return_value=_async_gen(
                _raw_result("c1", 0.9),
                _raw_result("c2", 0.7),
            )
        )
        adapter._client_wrapper.get_search_client = Mock(return_value=mock_client)

        results = await adapter.search(
            "idx",
            query_text="q",
            query_vector=[0.1] * 1536,
            search_mode=SearchMode.HYBRID,
            enable_reranker=False,
        )

        assert results[0].chunk_id == "c1"
        assert results[1].chunk_id == "c2"
