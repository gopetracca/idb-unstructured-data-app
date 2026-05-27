"""Integration tests for Azure AI Search with promoted metadata fields."""

import uuid
from datetime import datetime

import pytest

from src.config.settings import get_settings
from src.core.entities.vector_document import VectorDocument
from src.infrastructure.azure.adapters.vector_search_azure import AzureAISearchAdapter


@pytest.fixture
def search_adapter():
    """Create Azure AI Search adapter for integration tests."""
    settings = get_settings()
    return AzureAISearchAdapter(settings.vector_search)


@pytest.fixture
def unique_index_name():
    """Generate unique index name for test isolation."""
    return f"test-metadata-{uuid.uuid4().hex[:8]}"


@pytest.mark.integration
class TestAzureSearchMetadataIntegration:
    """Integration tests for Azure AI Search with promoted metadata."""

    async def test_create_index_with_promoted_metadata(
        self, search_adapter, unique_index_name
    ):
        """Test creating an index with promoted metadata fields."""
        try:
            # Create index
            result = await search_adapter.create_index(
                index_name=unique_index_name,
                schema={"vector_dimension": 1536, "document_category": "operational"},
            )

            assert result is True

            # Get index details
            index_info = await search_adapter.get_index(unique_index_name)

            assert index_info["name"] == unique_index_name
            assert index_info["vector_dimension"] == 1536

        finally:
            # Cleanup
            try:
                await search_adapter.delete_index(unique_index_name)
            except Exception:
                pass

    async def test_upsert_documents_with_enriched_metadata(
        self, search_adapter, unique_index_name
    ):
        """Test upserting documents with promoted metadata fields."""
        try:
            # Create index
            await search_adapter.create_index(
                index_name=unique_index_name,
                schema={"vector_dimension": 3, "document_category": "operational"},
            )

            # Create document with enriched metadata
            doc = VectorDocument(
                id="test_doc_1",
                chunk_id="chunk_0",
                file_id="file_1",
                text="Test document about transport infrastructure in Uruguay",
                vector=[0.1, 0.2, 0.3],
                metadata={
                    # Chunk-level metadata
                    "model_version": "text-embedding-3-small",
                    "token_count": 50,
                    "chunking_strategy": "sentence",
                    # Promoted document metadata
                    "operation_number": "UR-P1180",
                    "document_name": "Transport Infrastructure Project",
                    "document_author": "John Doe",
                    "sector": "TRANSPORT",
                    "country": "Uruguay",
                    "operation_type": "LOAN",
                    "dept_id": "EXR/CMG",
                    "disclosed": True,
                    "year": 2024,
                    "file_extension": ".pdf",
                    "document_publish_date": "2024-01-15T00:00:00Z",
                },
            )

            # Upsert document
            result = await search_adapter.upsert_documents(unique_index_name, [doc])

            assert len(result) == 1
            assert "test_doc_1" in result

        finally:
            # Cleanup
            try:
                await search_adapter.delete_index(unique_index_name)
            except Exception:
                pass

    async def test_search_filter_by_operation_number(
        self, search_adapter, unique_index_name
    ):
        """Test filtering search results by operation_number."""
        try:
            # Create index
            await search_adapter.create_index(
                index_name=unique_index_name,
                schema={"vector_dimension": 3, "document_category": "operational"},
            )

            # Create multiple documents
            docs = [
                VectorDocument(
                    id="doc_1",
                    chunk_id="chunk_0",
                    file_id="file_1",
                    text="Document about transport in Uruguay",
                    vector=[0.1, 0.2, 0.3],
                    metadata={
                        "operation_number": "UR-P1180",
                        "sector": "TRANSPORT",
                        "country": "Uruguay",
                    },
                ),
                VectorDocument(
                    id="doc_2",
                    chunk_id="chunk_0",
                    file_id="file_2",
                    text="Document about energy in Brazil",
                    vector=[0.4, 0.5, 0.6],
                    metadata={
                        "operation_number": "BR-E2345",
                        "sector": "ENERGY",
                        "country": "Brazil",
                    },
                ),
            ]

            await search_adapter.upsert_documents(unique_index_name, docs)

            # Wait for indexing
            import asyncio

            await asyncio.sleep(2)

            # Search with operation_number filter
            results = await search_adapter.search(
                index_name=unique_index_name,
                query_vector=[0.1, 0.2, 0.3],
                top_k=10,
                filters={"operation_number": "UR-P1180"},
            )

            assert len(results) > 0
            # All results should have operation_number UR-P1180
            for result in results:
                assert result.metadata.operation_number == "UR-P1180"

        finally:
            # Cleanup
            try:
                await search_adapter.delete_index(unique_index_name)
            except Exception:
                pass

    async def test_search_filter_by_sector(self, search_adapter, unique_index_name):
        """Test filtering search results by sector."""
        try:
            # Create index
            await search_adapter.create_index(
                index_name=unique_index_name,
                schema={"vector_dimension": 3, "document_category": "operational"},
            )

            # Create documents with different sectors
            docs = [
                VectorDocument(
                    id=f"transport_{i}",
                    chunk_id=f"chunk_{i}",
                    file_id=f"file_{i}",
                    text=f"Transport document {i}",
                    vector=[0.1 * i, 0.2 * i, 0.3 * i],
                    metadata={"sector": "TRANSPORT", "year": 2024},
                )
                for i in range(3)
            ] + [
                VectorDocument(
                    id=f"energy_{i}",
                    chunk_id=f"chunk_{i}",
                    file_id=f"file_{i + 10}",
                    text=f"Energy document {i}",
                    vector=[0.4 * i, 0.5 * i, 0.6 * i],
                    metadata={"sector": "ENERGY", "year": 2024},
                )
                for i in range(2)
            ]

            await search_adapter.upsert_documents(unique_index_name, docs)

            # Wait for indexing
            import asyncio

            await asyncio.sleep(2)

            # Search with sector filter
            results = await search_adapter.search(
                index_name=unique_index_name,
                query_vector=[0.1, 0.2, 0.3],
                top_k=10,
                filters={"sector": "TRANSPORT"},
            )

            assert len(results) > 0
            # All results should be TRANSPORT sector
            for result in results:
                assert result.metadata.sector == "TRANSPORT"

        finally:
            # Cleanup
            try:
                await search_adapter.delete_index(unique_index_name)
            except Exception:
                pass

    async def test_search_filter_by_country_list(
        self, search_adapter, unique_index_name
    ):
        """Test filtering by multiple countries (OR logic)."""
        try:
            # Create index
            await search_adapter.create_index(
                index_name=unique_index_name,
                schema={"vector_dimension": 3, "document_category": "operational"},
            )

            # Create documents from different countries
            docs = [
                VectorDocument(
                    id="uruguay_doc",
                    chunk_id="chunk_0",
                    file_id="file_1",
                    text="Uruguay transport project",
                    vector=[0.1, 0.2, 0.3],
                    metadata={"country": "Uruguay", "sector": "TRANSPORT"},
                ),
                VectorDocument(
                    id="brazil_doc",
                    chunk_id="chunk_0",
                    file_id="file_2",
                    text="Brazil energy project",
                    vector=[0.4, 0.5, 0.6],
                    metadata={"country": "Brazil", "sector": "ENERGY"},
                ),
                VectorDocument(
                    id="argentina_doc",
                    chunk_id="chunk_0",
                    file_id="file_3",
                    text="Argentina water project",
                    vector=[0.7, 0.8, 0.9],
                    metadata={"country": "Argentina", "sector": "WATER"},
                ),
            ]

            await search_adapter.upsert_documents(unique_index_name, docs)

            # Wait for indexing
            import asyncio

            await asyncio.sleep(2)

            # Search with multiple countries
            results = await search_adapter.search(
                index_name=unique_index_name,
                query_vector=[0.5, 0.5, 0.5],
                top_k=10,
                filters={"country": ["Uruguay", "Brazil"]},
            )

            assert len(results) > 0
            # All results should be from Uruguay or Brazil
            for result in results:
                assert result.metadata.country in ["Uruguay", "Brazil"]

        finally:
            # Cleanup
            try:
                await search_adapter.delete_index(unique_index_name)
            except Exception:
                pass

    async def test_search_filter_by_disclosed_boolean(
        self, search_adapter, unique_index_name
    ):
        """Test filtering by disclosed boolean field."""
        try:
            # Create index
            await search_adapter.create_index(
                index_name=unique_index_name,
                schema={"vector_dimension": 3, "document_category": "operational"},
            )

            # Create documents with different disclosure status
            docs = [
                VectorDocument(
                    id="disclosed_doc",
                    chunk_id="chunk_0",
                    file_id="file_1",
                    text="Public document",
                    vector=[0.1, 0.2, 0.3],
                    metadata={"disclosed": True, "document_name": "Public Report"},
                ),
                VectorDocument(
                    id="private_doc",
                    chunk_id="chunk_0",
                    file_id="file_2",
                    text="Private document",
                    vector=[0.4, 0.5, 0.6],
                    metadata={"disclosed": False, "document_name": "Private Report"},
                ),
            ]

            await search_adapter.upsert_documents(unique_index_name, docs)

            # Wait for indexing
            import asyncio

            await asyncio.sleep(2)

            # Search for disclosed documents only
            results = await search_adapter.search(
                index_name=unique_index_name,
                query_vector=[0.3, 0.3, 0.3],
                top_k=10,
                filters={"disclosed": True},
            )

            assert len(results) > 0
            # All results should be disclosed
            for result in results:
                assert result.metadata.disclosed is True

        finally:
            # Cleanup
            try:
                await search_adapter.delete_index(unique_index_name)
            except Exception:
                pass

    async def test_search_filter_by_year_range(
        self, search_adapter, unique_index_name
    ):
        """Test filtering by year range."""
        try:
            # Create index
            await search_adapter.create_index(
                index_name=unique_index_name,
                schema={"vector_dimension": 3, "document_category": "operational"},
            )

            # Create documents from different years
            docs = [
                VectorDocument(
                    id=f"doc_{year}",
                    chunk_id="chunk_0",
                    file_id=f"file_{year}",
                    text=f"Document from {year}",
                    vector=[0.1, 0.2, 0.3],
                    metadata={"year": year, "document_name": f"Report {year}"},
                )
                for year in [2020, 2022, 2024, 2025]
            ]

            await search_adapter.upsert_documents(unique_index_name, docs)

            # Wait for indexing
            import asyncio

            await asyncio.sleep(2)

            # Search for documents from 2022-2024
            results = await search_adapter.search(
                index_name=unique_index_name,
                query_vector=[0.1, 0.2, 0.3],
                top_k=10,
                filters={"year_min": 2022, "year_max": 2024},
            )

            assert len(results) > 0
            # All results should be within range
            for result in results:
                year = result.metadata.year
                assert 2022 <= year <= 2024

        finally:
            # Cleanup
            try:
                await search_adapter.delete_index(unique_index_name)
            except Exception:
                pass

    async def test_search_filter_combination(self, search_adapter, unique_index_name):
        """Test combining multiple filters (AND logic)."""
        try:
            # Create index
            await search_adapter.create_index(
                index_name=unique_index_name,
                schema={"vector_dimension": 3, "document_category": "operational"},
            )

            # Create diverse documents
            docs = [
                VectorDocument(
                    id="match_all",
                    chunk_id="chunk_0",
                    file_id="file_1",
                    text="Uruguay transport project 2024",
                    vector=[0.1, 0.2, 0.3],
                    metadata={
                        "country": "Uruguay",
                        "sector": "TRANSPORT",
                        "year": 2024,
                        "disclosed": True,
                    },
                ),
                VectorDocument(
                    id="wrong_country",
                    chunk_id="chunk_0",
                    file_id="file_2",
                    text="Brazil transport project 2024",
                    vector=[0.4, 0.5, 0.6],
                    metadata={
                        "country": "Brazil",
                        "sector": "TRANSPORT",
                        "year": 2024,
                        "disclosed": True,
                    },
                ),
                VectorDocument(
                    id="wrong_sector",
                    chunk_id="chunk_0",
                    file_id="file_3",
                    text="Uruguay energy project 2024",
                    vector=[0.7, 0.8, 0.9],
                    metadata={
                        "country": "Uruguay",
                        "sector": "ENERGY",
                        "year": 2024,
                        "disclosed": True,
                    },
                ),
            ]

            await search_adapter.upsert_documents(unique_index_name, docs)

            # Wait for indexing
            import asyncio

            await asyncio.sleep(2)

            # Search with multiple filters
            results = await search_adapter.search(
                index_name=unique_index_name,
                query_vector=[0.5, 0.5, 0.5],
                top_k=10,
                filters={
                    "country": "Uruguay",
                    "sector": "TRANSPORT",
                    "year": 2024,
                },
            )

            # Should only match the first document
            assert len(results) == 1
            assert results[0].metadata.country == "Uruguay"
            assert results[0].metadata.sector == "TRANSPORT"
            assert results[0].metadata.year == 2024

        finally:
            # Cleanup
            try:
                await search_adapter.delete_index(unique_index_name)
            except Exception:
                pass

    async def test_search_results_include_metadata(
        self, search_adapter, unique_index_name
    ):
        """Test that search results include enriched metadata fields."""
        try:
            # Create index
            await search_adapter.create_index(
                index_name=unique_index_name,
                schema={"vector_dimension": 3, "document_category": "operational"},
            )

            # Create document with full metadata
            doc = VectorDocument(
                id="full_metadata_doc",
                chunk_id="chunk_0",
                file_id="file_1",
                text="Complete document with all metadata",
                vector=[0.1, 0.2, 0.3],
                metadata={
                    "model_version": "text-embedding-3-small",
                    "token_count": 100,
                    "operation_number": "UR-P1180",
                    "document_name": "Complete Project Document",
                    "document_author": "Jane Smith",
                    "sector": "TRANSPORT",
                    "country": "Uruguay",
                    "operation_type": "LOAN",
                    "dept_id": "EXR/CMG",
                    "disclosed": True,
                    "year": 2024,
                    "file_extension": ".pdf",
                },
            )

            await search_adapter.upsert_documents(unique_index_name, [doc])

            # Wait for indexing
            import asyncio

            await asyncio.sleep(2)

            # Search without filters
            results = await search_adapter.search(
                index_name=unique_index_name,
                query_vector=[0.1, 0.2, 0.3],
                top_k=1,
            )

            assert len(results) == 1
            result = results[0]

            # Verify all metadata is present
            assert result.metadata.operation_number == "UR-P1180"
            assert result.metadata.document_name == "Complete Project Document"
            assert result.metadata.document_author == "Jane Smith"
            assert result.metadata.sector == "TRANSPORT"
            assert result.metadata.country == "Uruguay"
            assert result.metadata.year == 2024
            assert result.metadata.disclosed is True

        finally:
            # Cleanup
            try:
                await search_adapter.delete_index(unique_index_name)
            except Exception:
                pass
