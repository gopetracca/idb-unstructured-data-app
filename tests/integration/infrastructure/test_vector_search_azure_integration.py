"""Integration tests for AzureAISearchAdapter with real Azure AI Search service.

These tests require:
1. Azure AI Search service configured
2. Environment variables set:
   - VECTOR_SEARCH_ENDPOINT
   - VECTOR_SEARCH_API_KEY
   - VECTOR_SEARCH_RUN_TESTS=on
3. Sufficient quota for index creation and operations

Run with: pytest -m integration tests/integration/infrastructure/test_vector_search_azure_integration.py
"""

import asyncio
import random
import uuid
from typing import AsyncGenerator

import pytest

from src.config.settings import get_settings
from src.core.entities.search_result import SearchResult
from src.core.entities.vector_document import VectorDocument
from src.core.errors import IndexNotFoundError, VectorDatabaseError
from src.infrastructure.azure.adapters.vector_search_azure import AzureAISearchAdapter


@pytest.fixture
def settings():
    """Get vector search settings."""
    return get_settings().vector_search


@pytest.fixture
async def adapter(settings) -> AsyncGenerator[AzureAISearchAdapter, None]:
    """Create adapter with real Azure credentials."""
    if not settings.is_configured:
        pytest.skip("Azure AI Search not configured (missing endpoint or API key)")

    if not settings.run_tests_enabled:
        pytest.skip(
            "Integration tests disabled. Set VECTOR_SEARCH_RUN_TESTS=on to enable."
        )

    adapter = AzureAISearchAdapter(settings)
    yield adapter
    await adapter.close()


@pytest.fixture
async def test_index_name(adapter) -> AsyncGenerator[str, None]:
    """Create and cleanup test index."""
    # Use UUID to ensure unique index name for parallel test runs
    index_name = f"test-integration-{uuid.uuid4().hex[:8]}"

    # Setup: Create index with small vector dimension for speed
    await adapter.create_index(index_name, {"vector_dimension": 10, "document_category": "operational"})

    yield index_name

    # Cleanup: Delete the test index
    try:
        await adapter._client_wrapper.index_client.delete_index(index_name)
    except Exception as e:
        # Log but don't fail test cleanup
        print(f"Warning: Failed to cleanup index {index_name}: {e}")


@pytest.fixture
def sample_documents() -> list[VectorDocument]:
    """Create sample vector documents for testing."""
    return [
        VectorDocument(
            id=f"test-file1_chunk{i}",
            chunk_id=f"chunk{i}",
            file_id="test-file1",
            text=f"This is test content for chunk {i}",
            vector=[random.random() for _ in range(10)],
            metadata={
                "model_version": "test-v1",
                "token_count": 50 + i * 10,
                "chunking_strategy": "fixed_size",
                "chunk_size": 512,
                "overlap_chars": 50,
            },
        )
        for i in range(5)
    ]


@pytest.mark.integration
@pytest.mark.asyncio
class TestAzureAISearchIntegration:
    """Integration tests with real Azure AI Search service."""

    async def test_health_check(self, adapter):
        """Test health check with real service."""
        result = await adapter.health_check()
        assert result is True, "Health check should pass with valid credentials"

    async def test_create_index_success(self, adapter):
        """Test creating a real index."""
        index_name = f"test-create-{uuid.uuid4().hex[:8]}"

        try:
            # Add delay to avoid quota throttling
            await asyncio.sleep(1)
            result = await adapter.create_index(
                index_name, {"vector_dimension": 10, "document_category": "operational"}
            )
            assert result is True

            # Verify index exists
            result = await adapter.ensure_index(index_name)
            assert result is True

        finally:
            # Cleanup
            try:
                await adapter._client_wrapper.index_client.delete_index(index_name)
            except Exception:
                pass

    async def test_ensure_index_creates_if_not_exists(self, adapter):
        """Test ensure_index creates index when it doesn't exist."""
        index_name = f"test-ensure-{uuid.uuid4().hex[:8]}"

        try:
            # Add delay to avoid quota throttling
            await asyncio.sleep(1)
            # Should create the index
            result = await adapter.ensure_index(
                index_name, {"vector_dimension": 10, "document_category": "operational"}
            )
            assert result is True

            # Second call should just verify existence
            result = await adapter.ensure_index(index_name)
            assert result is True

        finally:
            # Cleanup
            try:
                await adapter._client_wrapper.index_client.delete_index(index_name)
            except Exception:
                pass

    async def test_upsert_documents_success(
        self, adapter, test_index_name, sample_documents
    ):
        """Test upserting documents to real index."""
        # Upsert documents
        inserted_ids = await adapter.upsert_documents(
            test_index_name, sample_documents
        )

        assert len(inserted_ids) == len(sample_documents)
        assert all(doc.id in inserted_ids for doc in sample_documents)

        # Wait for indexing to complete (Azure AI Search has ~2s latency)
        await asyncio.sleep(3)

        # Verify documents can be searched
        count = await adapter.get_document_count(test_index_name)
        assert count == len(sample_documents)

    async def test_upsert_updates_existing_documents(
        self, adapter, test_index_name, sample_documents
    ):
        """Test that upsert updates existing documents."""
        # Insert initial documents
        await adapter.upsert_documents(test_index_name, sample_documents)
        await asyncio.sleep(3)

        # Update the same documents with different text
        updated_docs = [
            VectorDocument(
                id=doc.id,
                chunk_id=doc.chunk_id,
                file_id=doc.file_id,
                text=f"UPDATED: {doc.text}",
                vector=doc.vector,
                metadata=doc.metadata,
            )
            for doc in sample_documents[:2]
        ]

        # Upsert (should update, not create duplicates)
        await adapter.upsert_documents(test_index_name, updated_docs)
        await asyncio.sleep(3)

        # Total count should remain the same
        count = await adapter.get_document_count(test_index_name)
        assert count == len(sample_documents)

    async def test_delete_documents_success(
        self, adapter, test_index_name, sample_documents
    ):
        """Test deleting documents from real index."""
        # Insert documents
        await adapter.upsert_documents(test_index_name, sample_documents)
        await asyncio.sleep(3)

        # Delete first two documents
        doc_ids_to_delete = [sample_documents[0].id, sample_documents[1].id]
        result = await adapter.delete_documents(test_index_name, doc_ids_to_delete)
        assert result is True

        # Wait for deletion to propagate
        await asyncio.sleep(3)

        # Verify count decreased
        count = await adapter.get_document_count(test_index_name)
        assert count == len(sample_documents) - 2

    async def test_delete_by_file_id_success(
        self, adapter, test_index_name, sample_documents
    ):
        """Test deleting all documents for a file."""
        # Insert documents
        await adapter.upsert_documents(test_index_name, sample_documents)
        await asyncio.sleep(3)

        # Delete all documents for test-file1
        deleted_count = await adapter.delete_by_file_id(
            test_index_name, "test-file1"
        )
        assert deleted_count == len(sample_documents)

        # Wait for deletion
        await asyncio.sleep(3)

        # Verify all documents deleted
        count = await adapter.get_document_count(test_index_name)
        assert count == 0

    async def test_vector_search_basic(
        self, adapter, test_index_name, sample_documents
    ):
        """Test basic vector similarity search."""
        # Insert documents
        await adapter.upsert_documents(test_index_name, sample_documents)
        await asyncio.sleep(3)

        # Search with a random query vector
        query_vector = [random.random() for _ in range(10)]
        results = await adapter.search(
            test_index_name, query_vector=query_vector, top_k=3
        )

        # Verify results
        assert len(results) <= 3
        assert all(isinstance(r, SearchResult) for r in results)
        assert all(0 <= r.score <= 1 for r in results)

        # Results should be sorted by score (descending)
        if len(results) > 1:
            assert results[0].score >= results[1].score

    async def test_vector_search_with_file_id_filter(
        self, adapter, test_index_name
    ):
        """Test vector search with file_ids filter."""
        # Insert documents from two different files
        docs_file1 = [
            VectorDocument(
                id=f"file1_chunk{i}",
                chunk_id=f"chunk{i}",
                file_id="file1",
                text=f"Content {i}",
                vector=[random.random() for _ in range(10)],
                metadata={"model_version": "v1", "token_count": 100},
            )
            for i in range(3)
        ]

        docs_file2 = [
            VectorDocument(
                id=f"file2_chunk{i}",
                chunk_id=f"chunk{i}",
                file_id="file2",
                text=f"Content {i}",
                vector=[random.random() for _ in range(10)],
                metadata={"model_version": "v1", "token_count": 100},
            )
            for i in range(3)
        ]

        await adapter.upsert_documents(test_index_name, docs_file1 + docs_file2)
        await asyncio.sleep(3)

        # Search with file_ids filter (using new filter format)
        query_vector = [random.random() for _ in range(10)]
        results = await adapter.search(
            test_index_name,
            query_vector=query_vector,
            top_k=10,
            filters={"file_ids": ["file1"]},
        )

        # All results should be from file1
        assert len(results) > 0
        assert all(r.file_id == "file1" for r in results)

    async def test_vector_search_with_metadata_filter(
        self, adapter, test_index_name
    ):
        """Test vector search with promoted metadata filters."""
        # Insert documents with different promoted metadata
        docs = [
            VectorDocument(
                id=f"file1_chunk{i}",
                chunk_id=f"chunk{i}",
                file_id="file1",
                text=f"Content {i}",
                vector=[random.random() for _ in range(10)],
                metadata={
                    "model_version": "v1",
                    "token_count": 100,
                    "chunking_strategy": "fixed_size",
                    "chunk_size": 512,
                    "overlap_chars": 50,
                    # Promoted metadata fields
                    "sector": "TRANSPORT" if i < 3 else "ENERGY",
                    "country": "Uruguay",
                    "year": 2024,
                },
            )
            for i in range(5)
        ]

        await adapter.upsert_documents(test_index_name, docs)
        await asyncio.sleep(3)

        # Search with promoted metadata filter for TRANSPORT sector
        query_vector = [random.random() for _ in range(10)]
        results = await adapter.search(
            test_index_name,
            query_vector=query_vector,
            top_k=10,
            filters={"sector": "TRANSPORT"},
        )

        # All results should have sector TRANSPORT
        assert len(results) > 0
        assert all(
            r.metadata.sector == "TRANSPORT" for r in results
        )

    async def test_search_empty_index_returns_empty_results(
        self, adapter, test_index_name
    ):
        """Test searching an empty index returns no results."""
        query_vector = [random.random() for _ in range(10)]
        results = await adapter.search(
            test_index_name, query_vector=query_vector, top_k=10
        )

        assert len(results) == 0

    async def test_search_nonexistent_index_raises_error(self, adapter):
        """Test searching non-existent index raises error."""
        query_vector = [random.random() for _ in range(10)]

        with pytest.raises(IndexNotFoundError):
            await adapter.search(
                "nonexistent-index-12345", query_vector=query_vector, top_k=10
            )

    async def test_delete_from_nonexistent_index_raises_error(self, adapter):
        """Test deleting from non-existent index raises error."""
        with pytest.raises(IndexNotFoundError):
            await adapter.delete_documents(
                "nonexistent-index-12345", ["doc1", "doc2"]
            )

    async def test_get_document_count(
        self, adapter, test_index_name, sample_documents
    ):
        """Test getting document count from index."""
        # Initially empty
        count = await adapter.get_document_count(test_index_name)
        assert count == 0

        # Insert documents
        await adapter.upsert_documents(test_index_name, sample_documents)
        await asyncio.sleep(3)

        # Count should match
        count = await adapter.get_document_count(test_index_name)
        assert count == len(sample_documents)

    async def test_context_manager_lifecycle(self, settings):
        """Test adapter lifecycle with async context manager."""
        if not settings.is_configured or not settings.run_tests_enabled:
            pytest.skip("Azure AI Search not configured or tests disabled")

        async with AzureAISearchAdapter(settings) as adapter:
            # Should be able to perform operations
            result = await adapter.health_check()
            assert result is True

        # After exiting context, adapter should have closed connections
        # (No way to verify this externally, but no errors should occur)

    async def test_batch_upsert_large_dataset(self, adapter, test_index_name):
        """Test upserting a large batch of documents."""
        # Create 150 documents to test batching (batch size is 1000)
        large_dataset = [
            VectorDocument(
                id=f"file1_chunk{i}",
                chunk_id=f"chunk{i}",
                file_id="file1",
                text=f"Content {i}",
                vector=[random.random() for _ in range(10)],
                metadata={
                    "model_version": "v1",
                    "token_count": 100,
                    "chunking_strategy": "fixed_size",
                    "chunk_size": 512,
                    "overlap_chars": 50,
                },
            )
            for i in range(150)
        ]

        # Upsert all documents
        inserted_ids = await adapter.upsert_documents(
            test_index_name, large_dataset
        )

        assert len(inserted_ids) == 150

        # Wait for indexing
        await asyncio.sleep(5)

        # Verify count
        count = await adapter.get_document_count(test_index_name)
        assert count == 150

    async def test_concurrent_operations(self, adapter, test_index_name):
        """Test that adapter handles concurrent operations correctly."""
        # Create different document sets
        docs_batch1 = [
            VectorDocument(
                id=f"batch1_chunk{i}",
                chunk_id=f"chunk{i}",
                file_id="batch1",
                text=f"Batch 1 content {i}",
                vector=[random.random() for _ in range(10)],
                metadata={"model_version": "batch1", "token_count": 100},
            )
            for i in range(5)
        ]

        docs_batch2 = [
            VectorDocument(
                id=f"batch2_chunk{i}",
                chunk_id=f"chunk{i}",
                file_id="batch2",
                text=f"Batch 2 content {i}",
                vector=[random.random() for _ in range(10)],
                metadata={"model_version": "batch2", "token_count": 100},
            )
            for i in range(5)
        ]

        # Upsert both batches concurrently
        results = await asyncio.gather(
            adapter.upsert_documents(test_index_name, docs_batch1),
            adapter.upsert_documents(test_index_name, docs_batch2),
        )

        # Both should succeed
        assert len(results[0]) == 5
        assert len(results[1]) == 5

        # Wait for indexing
        await asyncio.sleep(3)

        # Total count should be 10
        count = await adapter.get_document_count(test_index_name)
        assert count == 10

    @pytest.mark.slow
    async def test_search_performance(self, adapter, test_index_name):
        """Test search performance with realistic dataset."""
        # Create 100 documents
        docs = [
            VectorDocument(
                id=f"perf-test_chunk{i}",
                chunk_id=f"chunk{i}",
                file_id="perf-test",
                text=f"Performance test content chunk {i}",
                vector=[random.random() for _ in range(10)],
                metadata={
                    "model_version": "v1",
                    "token_count": 100,
                    "chunking_strategy": "fixed_size",
                    "chunk_size": 512,
                    "overlap_chars": 50,
                },
            )
            for i in range(100)
        ]

        # Insert documents
        await adapter.upsert_documents(test_index_name, docs)
        await asyncio.sleep(5)

        # Measure search time
        import time

        query_vector = [random.random() for _ in range(10)]

        start = time.time()
        results = await adapter.search(test_index_name, query_vector=query_vector, top_k=10)
        duration = time.time() - start

        # Verify results
        assert len(results) <= 10

        # Search should be fast (< 2 seconds for 100 docs)
        assert duration < 2.0, f"Search took {duration}s, expected < 2s"

        print(f"\nSearch performance: {duration:.3f}s for 100 documents")
