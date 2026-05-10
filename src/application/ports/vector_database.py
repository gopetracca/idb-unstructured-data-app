"""Port interface for vector database operations."""

from abc import ABC, abstractmethod
from typing import Any

from src.core.entities.search_result import SearchResult
from src.core.entities.vector_document import VectorDocument
from src.core.value_objects.search_mode import SearchMode


class VectorDatabasePort(ABC):
    """
    Abstract interface for vector database operations.

    This port defines the contract that any vector database implementation
    must fulfill, allowing for multiple backends (Azure AI Search, PostgreSQL+pgvector, etc.)
    without changing application logic.

    All methods are async to support non-blocking I/O operations.
    """

    @abstractmethod
    async def create_index(self, index_name: str, schema: dict[str, Any]) -> bool:
        """
        Create a new index/collection with specified schema.

        Args:
            index_name: Name of the index to create
            schema: Schema configuration (e.g., {"vector_dimension": 1536})

        Returns:
            True if index was created successfully

        Raises:
            IndexAlreadyExistsError: If index already exists
            VectorDatabaseError: If creation fails
        """
        pass

    @abstractmethod
    async def upsert_documents(
        self, index_name: str, documents: list[VectorDocument]
    ) -> list[str]:
        """
        Insert or update documents in the index.

        If a document with the same ID exists, it will be updated.
        Otherwise, a new document will be inserted.

        Args:
            index_name: Name of the index
            documents: List of VectorDocument instances to upsert

        Returns:
            List of document IDs that were successfully upserted

        Raises:
            IndexNotFoundError: If index doesn't exist
            VectorDatabaseError: If upsert operation fails
        """
        pass

    @abstractmethod
    async def delete_documents(self, index_name: str, document_ids: list[str]) -> bool:
        """
        Delete documents by their IDs.

        Args:
            index_name: Name of the index
            document_ids: List of document IDs to delete

        Returns:
            True if all documents were deleted successfully

        Raises:
            IndexNotFoundError: If index doesn't exist
            VectorDatabaseError: If delete operation fails
        """
        pass

    @abstractmethod
    async def delete_by_file_id(self, index_name: str, file_id: str) -> int:
        """
        Delete all documents (chunks) associated with a file.

        This is useful for cleaning up when a file is deleted from the system.

        Args:
            index_name: Name of the index
            file_id: File identifier

        Returns:
            Number of documents deleted

        Raises:
            IndexNotFoundError: If index doesn't exist
            VectorDatabaseError: If delete operation fails
        """
        pass

    @abstractmethod
    async def update_metadata_by_file_id(
        self,
        index_name: str,
        file_id: str,
        metadata_updates: dict[str, Any],
    ) -> int:
        """
        Update metadata fields for all chunks of a file in the index.

        Only document-level metadata fields should be passed. Chunk-level fields
        (page_number, section_path, has_table, etc.) are preserved from existing
        chunk data since they are not present in metadata_updates.

        Args:
            index_name: Name of the index
            file_id: File identifier
            metadata_updates: Dict of metadata fields to update (document-level only)

        Returns:
            Number of chunks updated

        Raises:
            IndexNotFoundError: If index doesn't exist
            VectorDatabaseError: If update operation fails
        """
        pass

    @abstractmethod
    async def search(
        self,
        index_name: str,
        query_text: str | None = None,
        query_vector: list[float] | None = None,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        search_mode: SearchMode = SearchMode.SEMANTIC,
        enable_reranker: bool = False,
        reranker_profile: str | None = None,
    ) -> list[SearchResult]:
        """
        Perform search using the specified mode.

        Args:
            index_name: Name of the index to search
            query_text: Query text (required for keyword/hybrid modes)
            query_vector: Query embedding vector (required for semantic/hybrid modes)
            top_k: Number of results to return (default: 10)
            filters: Optional metadata filters (e.g., {"file_id": "abc123"})
            search_mode: Search mode — semantic (vector-only), keyword (BM25), or hybrid (RRF)
            enable_reranker: Apply Azure semantic L2 reranker when True (hybrid/keyword modes)
            reranker_profile: Optional semantic reranker profile (Azure semantic configuration name)

        Returns:
            List of SearchResult instances, sorted by relevance (highest score first)

        Raises:
            IndexNotFoundError: If index doesn't exist
            VectorDatabaseError: If search operation fails
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the vector database is accessible and healthy.

        Returns:
            True if database is accessible, False otherwise

        Note:
            This method should not raise exceptions, but return False on error.
        """
        pass

    @abstractmethod
    async def ensure_index(self, index_name: str, schema: dict[str, Any] | None = None) -> bool:
        """
        Ensure that an index exists, creating it if necessary.

        Args:
            index_name: Name of the index
            schema: Optional schema for index creation (e.g., {"vector_dimension": 1536})

        Returns:
            True if index exists or was created successfully

        Raises:
            VectorDatabaseError: If index check or creation fails

        Example:
            >>> await db.ensure_index("embeddings", {"vector_dimension": 1536})
        """
        pass

    @abstractmethod
    async def get_document_count(self, index_name: str) -> int:
        """
        Get the total number of documents in an index.

        Args:
            index_name: Name of the index

        Returns:
            Number of documents in the index

        Raises:
            IndexNotFoundError: If index doesn't exist
            VectorDatabaseError: If operation fails
        """
        pass

    @abstractmethod
    async def list_indexes(self) -> list[dict[str, Any]]:
        """
        List all indexes/collections.

        Returns:
            List of index metadata dictionaries containing:
            - name: Index name
            - vector_dimension: Vector dimension size
            - document_count: Number of documents (if available)
            - created_at: Creation timestamp (if available)

        Raises:
            VectorDatabaseError: If operation fails

        Example:
            >>> indexes = await db.list_indexes()
            >>> for index in indexes:
            ...     print(f"{index['name']}: {index['document_count']} docs")
        """
        pass

    @abstractmethod
    async def get_index(self, index_name: str) -> dict[str, Any]:
        """
        Get detailed information about an index.

        Args:
            index_name: Name of the index

        Returns:
            Index metadata dictionary containing:
            - name: Index name
            - vector_dimension: Vector dimension size
            - document_count: Number of documents
            - schema: Field definitions
            - created_at: Creation timestamp (if available)
            - last_updated: Last update timestamp (if available)

        Raises:
            IndexNotFoundError: If index doesn't exist
            VectorDatabaseError: If operation fails

        Example:
            >>> index = await db.get_index("embeddings")
            >>> print(f"Dimension: {index['vector_dimension']}")
        """
        pass

    @abstractmethod
    async def configure_reranker(
        self,
        index_name: str,
        enabled: bool,
        semantic_configuration_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Enable or disable the semantic L2 reranker on an existing index.

        When enabling, attaches a SemanticConfiguration to the index (safe to call
        on indexes that already have one — it updates in place).  When disabling,
        removes the SemanticConfiguration.

        Args:
            index_name: Name of the index
            enabled: True to enable, False to disable
            semantic_configuration_name: Override the config name (uses the service
                default when None)

        Returns:
            Dict with keys: index_name, reranker_enabled, semantic_configuration_name

        Raises:
            IndexNotFoundError: If the index does not exist
            VectorDatabaseError: If the operation fails
        """
        pass

    @abstractmethod
    async def delete_index(self, index_name: str) -> bool:
        """
        Delete an index and all its documents.

        Args:
            index_name: Name of the index to delete

        Returns:
            True if deleted successfully

        Raises:
            IndexNotFoundError: If index doesn't exist
            VectorDatabaseError: If operation fails

        Warning:
            This operation is irreversible and will delete all documents
            in the index. Use with caution.

        Example:
            >>> deleted = await db.delete_index("old-embeddings")
            >>> print(f"Index deleted: {deleted}")
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """
        Close database connections and release resources.

        This method should be called when the database client is no longer needed,
        typically in an async context manager's __aexit__ method.
        """
        pass
