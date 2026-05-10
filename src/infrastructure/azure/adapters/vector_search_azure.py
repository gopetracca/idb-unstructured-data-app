"""Azure AI Search adapter implementing VectorDatabasePort."""

import asyncio
import json
import logging
from typing import Any

from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.search.documents.indexes.models import (
    ComplexField,
    HnswAlgorithmConfiguration,
    SearchableField,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from azure.search.documents.models import QueryType, VectorizedQuery

from src.application.ports.vector_database import VectorDatabasePort
from src.config.settings import VectorSearchSettings, get_settings
from src.core.entities.search_result import SearchResult
from src.core.entities.vector_document import VectorDocument
from src.core.errors import (
    IndexAlreadyExistsError,
    IndexNotFoundError,
    VectorDatabaseError,
    VectorDimensionMismatchError,
)
from src.core.index_schemas import get_index_schema, list_document_types
from src.infrastructure.azure.adapters.index_schema_mapper import to_azure_search_field
from src.core.value_objects.searchable_metadata import SearchableMetadata
from src.core.value_objects.search_mode import SearchMode
from src.infrastructure.azure.clients.search_client import SearchClientWrapper

logger = logging.getLogger(__name__)


class AzureAISearchAdapter(VectorDatabasePort):
    """
    Azure AI Search implementation of VectorDatabasePort.

    This adapter enables vector similarity search using Azure AI Search's
    HNSW (Hierarchical Navigable Small World) algorithm for efficient
    approximate nearest neighbor search.

    Features:
    - HNSW vector indexing with configurable parameters
    - ComplexField metadata for advanced filtering
    - Async operations throughout
    - Batch document operations (up to 1000 docs)
    - Proper error handling and retry logic

    Example:
        >>> settings = VectorSearchSettings(...)
        >>> async with AzureAISearchAdapter(settings) as adapter:
        ...     await adapter.create_index("embeddings", {"vector_dimension": 1536})
        ...     await adapter.upsert_documents("embeddings", documents)
        ...     results = await adapter.search("embeddings", query_vector, top_k=10)
    """

    def __init__(self, settings: VectorSearchSettings | None = None):
        """
        Initialize the Azure AI Search adapter.

        Args:
            settings: Optional VectorSearchSettings instance.
                     If None, loads from global settings.
        """
        self._settings = settings or get_settings().vector_search
        self._client_wrapper = SearchClientWrapper(
            endpoint=self._settings.endpoint,
            api_key=self._settings.api_key,
            managed_identity_client_id=get_settings().azure_client_id,
        )


        logger.info(
            f"Initialized AzureAISearchAdapter for endpoint: {self._settings.endpoint}"
        )

    def _create_base_fields(self, vector_dimension: int) -> list[SearchField]:
        """
        Create the top-level fields present in every index.

        These fields are fixed regardless of document type: id, chunkId, fileId,
        content (full-text), and contentVector (embeddings).

        Args:
            vector_dimension: Dimensionality of the embedding vectors

        Returns:
            List of top-level SearchField definitions
        """
        return [
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SimpleField(
                name="chunkId",
                type=SearchFieldDataType.String,
                filterable=True,
                sortable=True,
            ),
            SimpleField(
                name="fileId",
                type=SearchFieldDataType.String,
                filterable=True,
                sortable=True,
            ),
            SearchableField(name="content", type=SearchFieldDataType.String),
            SearchField(
                name="contentVector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=vector_dimension,
                vector_search_profile_name="default-hnsw-profile",
            ),
        ]

    def _create_metadata_fields(self, document_type: str) -> list[SearchField]:
        """
        Create metadata fields from the Index Schema Registry.

        Converts the declarative IndexFieldSpec definitions into Azure SearchField
        objects for the metadata ComplexField.

        Args:
            document_type: Type of document (e.g., "operational", "publication")

        Returns:
            List of SearchField definitions for the metadata ComplexField
        """
        schema = get_index_schema(document_type)
        fields = [to_azure_search_field(spec) for spec in schema]
        logger.debug(
            f"Created {len(fields)} metadata fields from registry for '{document_type}'"
        )
        return fields

    def _create_index_fields(
        self, vector_dimension: int, document_type: str
    ) -> list[SearchField]:
        """
        Assemble the full set of index fields for a document type.

        Combines the fixed base fields with the document-type-specific metadata
        ComplexField generated from the Index Schema Registry.

        Args:
            vector_dimension: Dimensionality of the embedding vectors
            document_type: Type of document for schema selection (default: "operational")

        Returns:
            List of SearchField definitions for the index schema
        """
        base_fields = self._create_base_fields(vector_dimension)
        metadata_fields = self._create_metadata_fields(document_type)
        return base_fields + [ComplexField(name="metadata", fields=metadata_fields)]

    async def create_index(self, index_name: str, schema: dict[str, Any]) -> bool:
        """
        Create a new search index with vector search configuration.

        Args:
            index_name: Name of the index to create
            schema: Schema configuration with the following keys:
                - document_type (str): REQUIRED. Type of documents this index will hold
                  (e.g., "operational", "publication")
                - vector_dimension (int): Embedding vector size (default: 1536)
                - embedding_model (str): Model name (default: "text-embedding-3-small")

        Returns:
            True if index was created successfully

        Raises:
            ValueError: If document_type is missing or not recognized
            IndexAlreadyExistsError: If index already exists
            VectorDatabaseError: If creation fails
        """
        try:
            vector_dimension = schema.get("vector_dimension", 1536)
            embedding_model = schema.get("embedding_model", "text-embedding-3-small")

            document_type = schema.get("document_type")
            if not document_type:
                raise ValueError(
                    "schema must include 'document_type' "
                    f"(available: {', '.join(list_document_types())})"
                )

            # Validate document_type against registry
            available_types = list_document_types()
            if document_type not in available_types:
                raise ValueError(
                    f"Unknown document_type: '{document_type}'. "
                    f"Available types: {', '.join(available_types)}"
                )

            logger.info(
                f"Creating index '{index_name}' with vector dimension: {vector_dimension}, "
                f"embedding model: {embedding_model}, document_type: {document_type}"
            )

            # Define index fields using helper method with document_type
            fields = self._create_index_fields(vector_dimension, document_type)

            # Configure HNSW vector search
            vector_search = VectorSearch(
                algorithms=[
                    HnswAlgorithmConfiguration(
                        name="default-hnsw",
                        parameters={
                            "m": self._settings.hnsw_m,
                            "efConstruction": self._settings.hnsw_ef_construction,
                            "efSearch": self._settings.hnsw_ef_search,
                            "metric": "cosine",  # Cosine similarity
                        },
                    )
                ],
                profiles=[
                    VectorSearchProfile(
                        name="default-hnsw-profile",
                        algorithm_configuration_name="default-hnsw",
                    )
                ],
            )

            # Store index metadata in description as JSON — reranker is off by default
            # at creation time; use configure_reranker() to enable it later.
            metadata = {
                "embedding_model": embedding_model,
                "document_type": document_type,
                "reranker_enabled": False,
                "semantic_configuration_name": None,
            }
            description = json.dumps(metadata)

            # No SemanticConfiguration at creation time; added on demand via configure_reranker()
            semantic_search = None

            # Create index (no semantic config yet — added via configure_reranker)
            index = SearchIndex(
                name=index_name,
                fields=fields,
                vector_search=vector_search,
                description=description,
            )

            await self._client_wrapper.index_client.create_or_update_index(index)

            logger.info(f"Successfully created index: {index_name}")
            return True

        except ValueError:
            raise  # Validation errors (missing/unknown document_type) bubble up as-is
        except ResourceNotFoundError as e:
            logger.error(f"Index creation failed - resource not found: {e}")
            raise VectorDatabaseError(
                f"Failed to create index '{index_name}': {e}",
                index_name=index_name,
                operation="create_index",
            )
        except Exception as e:
            logger.error(f"Failed to create index '{index_name}': {e}", exc_info=True)
            raise VectorDatabaseError(
                f"Failed to create index '{index_name}': {e}",
                index_name=index_name,
                operation="create_index",
            )

    async def create_operational_index(
        self,
        index_name: str,
        vector_dimension: int = 1536,
        embedding_model: str = "text-embedding-3-small",
    ) -> bool:
        """
        Create an index for operational documents (loans, grants, TCs).

        Convenience wrapper around create_index() with document_type="operational".

        Args:
            index_name: Name for the new index
            vector_dimension: Embedding vector size (default: 1536)
            embedding_model: Model used for embeddings

        Returns:
            True if created successfully
        """
        return await self.create_index(
            index_name,
            {
                "vector_dimension": vector_dimension,
                "document_type": "operational",
                "embedding_model": embedding_model,
            },
        )

    async def create_publication_index(
        self,
        index_name: str,
        vector_dimension: int = 1536,
        embedding_model: str = "text-embedding-3-small",
    ) -> bool:
        """
        Create an index for research publications.

        Convenience wrapper around create_index() with document_type="publication".

        Args:
            index_name: Name for the new index
            vector_dimension: Embedding vector size (default: 1536)
            embedding_model: Model used for embeddings

        Returns:
            True if created successfully
        """
        return await self.create_index(
            index_name,
            {
                "vector_dimension": vector_dimension,
                "document_type": "publication",
                "embedding_model": embedding_model,
            },
        )

    async def upsert_documents(
        self, index_name: str, documents: list[VectorDocument]
    ) -> list[str]:
        """
        Insert or update documents in the index.

        Args:
            index_name: Name of the index
            documents: List of VectorDocument instances to upsert

        Returns:
            List of document IDs that were successfully upserted

        Raises:
            IndexNotFoundError: If index doesn't exist
            VectorDatabaseError: If upsert operation fails
        """
        if not documents:
            logger.warning("No documents to upsert")
            return []

        try:
            client = self._client_wrapper.get_search_client(index_name)

            logger.info(
                f"Upserting {len(documents)} documents to index '{index_name}'"
            )

            # Transform VectorDocument to Azure Search schema
            search_docs = [
                {
                    "id": doc.id,
                    "chunkId": doc.chunk_id,
                    "fileId": doc.file_id,
                    "content": doc.text,
                    "contentVector": doc.vector,
                    "metadata": doc.metadata.model_dump(exclude_none=True),
                }
                for doc in documents
            ]

            # Batch upsert (max 1000 docs per call)
            batch_size = min(self._settings.batch_size, 1000)
            successful_ids = []

            for i in range(0, len(search_docs), batch_size):
                batch = search_docs[i : i + batch_size]

                logger.debug(
                    f"Upserting batch {i // batch_size + 1}: {len(batch)} documents"
                )

                result = await client.merge_or_upload_documents(documents=batch)

                # Collect successful IDs
                batch_successful = [r.key for r in result if r.succeeded]
                successful_ids.extend(batch_successful)

                # Log failures
                failed = [r for r in result if not r.succeeded]
                if failed:
                    logger.warning(
                        f"Failed to upsert {len(failed)} documents in batch: "
                        f"{[r.key for r in failed[:5]]}"
                    )

            logger.info(
                f"Successfully upserted {len(successful_ids)} out of {len(documents)} documents"
            )

            return successful_ids

        except HttpResponseError as e:
            if e.status_code == 404:
                raise IndexNotFoundError(index_name)
            elif e.status_code == 429:
                logger.warning("Rate limit exceeded, implement retry logic")
                raise VectorDatabaseError(
                    "Rate limit exceeded",
                    index_name=index_name,
                    operation="upsert_documents",
                    details={"status_code": 429},
                )
            else:
                raise VectorDatabaseError(
                    f"Failed to upsert documents: {e}",
                    index_name=index_name,
                    operation="upsert_documents",
                )
        except Exception as e:
            logger.error(
                f"Failed to upsert documents to '{index_name}': {e}", exc_info=True
            )
            raise VectorDatabaseError(
                f"Failed to upsert documents: {e}",
                index_name=index_name,
                operation="upsert_documents",
            )

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
        if not document_ids:
            logger.warning("No document IDs to delete")
            return True

        try:
            client = self._client_wrapper.get_search_client(index_name)

            logger.info(
                f"Deleting {len(document_ids)} documents from index '{index_name}'"
            )

            documents = [{"id": doc_id} for doc_id in document_ids]
            result = await client.delete_documents(documents=documents)

            successful = all(r.succeeded for r in result)

            if successful:
                logger.info(f"Successfully deleted {len(document_ids)} documents")
            else:
                failed = [r.key for r in result if not r.succeeded]
                logger.warning(f"Failed to delete {len(failed)} documents: {failed[:5]}")

            return successful

        except HttpResponseError as e:
            if e.status_code == 404:
                raise IndexNotFoundError(index_name)
            raise VectorDatabaseError(
                f"Failed to delete documents: {e}",
                index_name=index_name,
                operation="delete_documents",
            )
        except Exception as e:
            logger.error(
                f"Failed to delete documents from '{index_name}': {e}", exc_info=True
            )
            raise VectorDatabaseError(
                f"Failed to delete documents: {e}",
                index_name=index_name,
                operation="delete_documents",
            )

    async def delete_by_file_id(self, index_name: str, file_id: str) -> int:
        """
        Delete all documents (chunks) associated with a file.

        Args:
            index_name: Name of the index
            file_id: File identifier

        Returns:
            Number of documents deleted

        Raises:
            IndexNotFoundError: If index doesn't exist
            VectorDatabaseError: If delete operation fails
        """
        try:
            client = self._client_wrapper.get_search_client(index_name)

            logger.info(f"Deleting all documents for file_id '{file_id}' from '{index_name}'")

            # Search for all documents with this file_id
            results = await client.search(
                search_text="*", filter=f"fileId eq '{file_id}'", select=["id"]
            )

            # Collect document IDs
            doc_ids = []
            async for r in results:
                doc_ids.append(r["id"])

            if not doc_ids:
                logger.info(f"No documents found for file_id '{file_id}'")
                return 0

            # Delete documents
            await self.delete_documents(index_name, doc_ids)

            logger.info(f"Deleted {len(doc_ids)} documents for file_id '{file_id}'")
            return len(doc_ids)

        except IndexNotFoundError:
            raise
        except Exception as e:
            logger.error(
                f"Failed to delete by file_id '{file_id}' from '{index_name}': {e}",
                exc_info=True,
            )
            raise VectorDatabaseError(
                f"Failed to delete by file_id: {e}",
                index_name=index_name,
                operation="delete_by_file_id",
            )

    async def update_metadata_by_file_id(
        self,
        index_name: str,
        file_id: str,
        metadata_updates: dict[str, Any],
    ) -> int:
        """
        Update metadata fields for all chunks of a file in the index.

        Reads existing chunk metadata, merges updates in Python (preserving
        chunk-level fields), and writes back using merge_or_upload_documents.

        Args:
            index_name: Name of the index
            file_id: File identifier
            metadata_updates: Dict of document-level metadata fields to update

        Returns:
            Number of chunks updated

        Raises:
            IndexNotFoundError: If index doesn't exist
            VectorDatabaseError: If update operation fails
        """
        if not metadata_updates:
            logger.info(f"No metadata updates provided for file_id '{file_id}', skipping")
            return 0

        try:
            client = self._client_wrapper.get_search_client(index_name)

            logger.info(
                f"Updating metadata for file_id '{file_id}' in '{index_name}', "
                f"fields={list(metadata_updates.keys())}"
            )

            # Retrieve existing chunks with their current metadata
            results = await client.search(
                search_text="*",
                filter=f"fileId eq '{file_id}'",
                select=["id", "metadata"],
            )

            chunks = [chunk async for chunk in results]

            if not chunks:
                logger.info(f"No chunks found for file_id '{file_id}'")
                return 0

            # Merge updates into each chunk's metadata, preserving chunk-level fields.
            # Azure AI Search replaces the entire complex field on merge, so we must
            # read the full current metadata and merge in Python before writing back.
            merged_docs = []
            for chunk in chunks:
                current_metadata = dict(chunk.get("metadata") or {})
                current_metadata.update(metadata_updates)
                merged_docs.append({"id": chunk["id"], "metadata": current_metadata})

            # Batch upsert
            batch_size = min(self._settings.batch_size, 1000)
            for i in range(0, len(merged_docs), batch_size):
                batch = merged_docs[i : i + batch_size]
                result = await client.merge_or_upload_documents(documents=batch)
                failed = [r for r in result if not r.succeeded]
                if failed:
                    logger.warning(
                        f"Failed to update metadata for {len(failed)} chunks of "
                        f"file_id '{file_id}': {[r.key for r in failed[:5]]}"
                    )

            logger.info(
                f"Updated metadata for {len(merged_docs)} chunks of file_id '{file_id}'"
            )
            return len(merged_docs)

        except HttpResponseError as e:
            if e.status_code == 404:
                raise IndexNotFoundError(index_name)
            raise VectorDatabaseError(
                f"Failed to update metadata by file_id: {e}",
                index_name=index_name,
                operation="update_metadata_by_file_id",
            )
        except Exception as e:
            logger.error(
                f"Failed to update metadata for file_id '{file_id}' in '{index_name}': {e}",
                exc_info=True,
            )
            raise VectorDatabaseError(
                f"Failed to update metadata by file_id: {e}",
                index_name=index_name,
                operation="update_metadata_by_file_id",
            )

    def _escape_odata_string(self, value: str) -> str:
        """Escape OData string literals."""
        return value.replace("'", "''")

    def _build_filter_string(self, filters: dict[str, Any]) -> str | None:
        """
        Build OData filter string from filter dict including promoted document metadata.

        Supported filters:
        - file_ids: List[str] - Multiple file IDs (OR logic)
        - document_type: str - Exact match
        - tags: List[str] | str - AND logic across tags
        - department: str - Exact match
        - source: str - Exact match
        - operation_number: str - Exact match
        - sector: str | List[str] - Exact match or multiple values (OR logic)
        - country: str | List[str] - Exact match or multiple values (OR logic)
        - operation_type: str - Exact match
        - dept_id: str - Exact match
        - disclosed: bool - Boolean match
        - year: int - Exact match
        - year_min, year_max: int - Range boundaries
        - document_author: str - Partial text match using search.ismatch()
        - file_extension: str - Exact match
        - document_name: str - Exact match
        - ezshare_id: str - Exact match
        - document_publish_date_from, document_publish_date_to: str - Date range (ISO format)

        Args:
            filters: Dictionary of filter criteria

        Returns:
            OData filter string or None if no filters
        """
        if not filters:
            return None

        filter_parts = []

        # Existing: file_ids filter (OR logic)
        if "file_ids" in filters and filters["file_ids"]:
            file_id_filters = " or ".join(
                [f"fileId eq '{self._escape_odata_string(fid)}'" for fid in filters["file_ids"]]
            )
            filter_parts.append(f"({file_id_filters})")

        # NEW: Promoted document metadata filters

        # Operation number (exact match)
        if "operation_number" in filters and filters["operation_number"]:
            filter_parts.append(
                f"metadata/operation_number eq '{self._escape_odata_string(filters['operation_number'])}'"
            )

        # Sector (exact match or list)
        if "sector" in filters and filters["sector"]:
            if isinstance(filters["sector"], list):
                sector_filters = " or ".join(
                    [
                        f"metadata/sector eq '{self._escape_odata_string(s)}'"
                        for s in filters["sector"]
                    ]
                )
                filter_parts.append(f"({sector_filters})")
            else:
                filter_parts.append(
                    f"metadata/sector eq '{self._escape_odata_string(filters['sector'])}'"
                )

        # Country (exact match or list)
        if "country" in filters and filters["country"]:
            if isinstance(filters["country"], list):
                country_filters = " or ".join(
                    [
                        f"metadata/country eq '{self._escape_odata_string(c)}'"
                        for c in filters["country"]
                    ]
                )
                filter_parts.append(f"({country_filters})")
            else:
                filter_parts.append(
                    f"metadata/country eq '{self._escape_odata_string(filters['country'])}'"
                )

        # Operation type
        if "operation_type" in filters and filters["operation_type"]:
            filter_parts.append(
                f"metadata/operation_type eq '{self._escape_odata_string(filters['operation_type'])}'"
            )

        # Department ID
        if "dept_id" in filters and filters["dept_id"]:
            filter_parts.append(
                f"metadata/dept_id eq '{self._escape_odata_string(filters['dept_id'])}'"
            )

        # Disclosed (boolean)
        if "disclosed" in filters and filters["disclosed"] is not None:
            filter_parts.append(
                f"metadata/disclosed eq {str(filters['disclosed']).lower()}"
            )

        # Year (exact match)
        if "year" in filters and filters["year"]:
            filter_parts.append(f"metadata/year eq {filters['year']}")

        # Year range
        if "year_min" in filters and filters["year_min"]:
            filter_parts.append(f"metadata/year ge {filters['year_min']}")
        if "year_max" in filters and filters["year_max"]:
            filter_parts.append(f"metadata/year le {filters['year_max']}")

        # Document author (partial match using search.ismatch)
        if "document_author" in filters and filters["document_author"]:
            # Escape single quotes for OData
            author = self._escape_odata_string(filters["document_author"])
            filter_parts.append(
                f"search.ismatch('{author}', 'metadata/document_author')"
            )

        # File extension
        if "file_extension" in filters and filters["file_extension"]:
            extension = filters["file_extension"]
            # Ensure extension starts with dot
            if not extension.startswith("."):
                extension = f".{extension}"
            filter_parts.append(
                f"metadata/file_extension eq '{self._escape_odata_string(extension)}'"
            )

        # Document name
        if "document_name" in filters and filters["document_name"]:
            filter_parts.append(
                f"metadata/document_name eq '{self._escape_odata_string(filters['document_name'])}'"
            )

        # Document type
        if "document_type" in filters and filters["document_type"]:
            filter_parts.append(
                f"metadata/document_type eq '{self._escape_odata_string(filters['document_type'])}'"
            )

        # Department
        if "department" in filters and filters["department"]:
            filter_parts.append(
                f"metadata/department eq '{self._escape_odata_string(filters['department'])}'"
            )

        # Source
        if "source" in filters and filters["source"]:
            filter_parts.append(
                f"metadata/source eq '{self._escape_odata_string(filters['source'])}'"
            )

        # Tags (AND logic)
        if "tags" in filters and filters["tags"]:
            tags = filters["tags"]
            if isinstance(tags, list):
                tag_filters = " and ".join(
                    [
                        f"metadata/tags/any(t: t eq '{self._escape_odata_string(tag)}')"
                        for tag in tags
                    ]
                )
                filter_parts.append(f"({tag_filters})")
            else:
                filter_parts.append(
                    f"metadata/tags/any(t: t eq '{self._escape_odata_string(str(tags))}')"
                )

        # EZShare ID
        if "ezshare_id" in filters and filters["ezshare_id"]:
            filter_parts.append(
                f"metadata/ezshare_id eq '{self._escape_odata_string(filters['ezshare_id'])}'"
            )

        # Document publish date range
        if "document_publish_date_from" in filters and filters["document_publish_date_from"]:
            filter_parts.append(
                f"metadata/document_publish_date ge {filters['document_publish_date_from']}"
            )
        if "document_publish_date_to" in filters and filters["document_publish_date_to"]:
            filter_parts.append(
                f"metadata/document_publish_date le {filters['document_publish_date_to']}"
            )

        # Combine all filter parts with AND logic
        if not filter_parts:
            return None

        filter_string = " and ".join(filter_parts)
        logger.debug(f"Built OData filter string: {filter_string}")
        return filter_string

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
        Perform search using the specified mode (semantic/keyword/hybrid).

        Args:
            index_name: Name of the index to search
            query_text: Query text (required for keyword/hybrid modes)
            query_vector: Query embedding vector (required for semantic/hybrid modes)
            top_k: Number of results to return
            filters: Optional metadata filters
            search_mode: semantic (vector-only), keyword (BM25), or hybrid (RRF)
            enable_reranker: Apply Azure semantic L2 reranker when True
            reranker_profile: Optional semantic reranker profile (Azure semantic configuration name)

        Returns:
            List of SearchResult instances sorted by reranker_score (when enabled) or score desc

        Raises:
            IndexNotFoundError: If index doesn't exist
            VectorDatabaseError: If search operation fails
        """
        try:
            client = self._client_wrapper.get_search_client(index_name)

            logger.debug(
                f"Searching index '{index_name}' mode={search_mode} reranker={enable_reranker} top_k={top_k}"
            )

            filter_str = self._build_filter_string(filters) if filters else None

            # Build vector_queries only when the mode uses vectors
            vector_queries: list[VectorizedQuery] | None = None
            if search_mode in (SearchMode.SEMANTIC, SearchMode.HYBRID) and query_vector is not None:
                vector_queries = [
                    VectorizedQuery(
                        vector=query_vector,
                        k_nearest_neighbors=50,
                        fields="contentVector",
                    )
                ]

            # search_text drives BM25 in keyword/hybrid modes
            search_text: str | None = query_text if search_mode in (SearchMode.KEYWORD, SearchMode.HYBRID) else None

            # Build keyword args for semantic reranker
            extra_kwargs: dict[str, Any] = {}
            if enable_reranker and search_mode in (SearchMode.KEYWORD, SearchMode.HYBRID):
                semantic_configuration_name = (
                    reranker_profile or self._settings.semantic_configuration_name
                )
                extra_kwargs["query_type"] = QueryType.SEMANTIC
                extra_kwargs["semantic_configuration_name"] = semantic_configuration_name
                extra_kwargs["query_caption"] = "extractive"
                extra_kwargs["query_answer"] = "extractive"
            results = await client.search(
                search_text=search_text,
                vector_queries=vector_queries,
                filter=filter_str,
                select=["id", "chunkId", "fileId", "content", "metadata"],
                top=top_k,
                **extra_kwargs,
            )

            search_results = []
            async for r in results:
                raw_metadata = r.get("metadata") or {}
                metadata = SearchableMetadata.model_validate(raw_metadata)
                reranker_score = r.get("@search.reranker_score")
                search_results.append(
                    SearchResult(
                        chunk_id=r["chunkId"],
                        file_id=r["fileId"],
                        text=r["content"],
                        score=r["@search.score"],
                        reranker_score=reranker_score,
                        metadata=metadata,
                    )
                )

            # Sort by reranker_score desc when present, else score desc (Azure already returns
            # results sorted, but reranker_score may reorder them)
            if enable_reranker and any(r.reranker_score is not None for r in search_results):
                search_results.sort(
                    key=lambda r: r.reranker_score if r.reranker_score is not None else -1.0,
                    reverse=True,
                )

            logger.info(f"Found {len(search_results)} results for '{index_name}' ({search_mode})")
            return search_results

        except HttpResponseError as e:
            if e.status_code == 404:
                raise IndexNotFoundError(index_name)
            raise VectorDatabaseError(
                f"Search failed: {e}",
                index_name=index_name,
                operation="search",
                details={
                    "status_code": e.status_code,
                    "reason": getattr(e, "reason", None),
                    "error": str(e),
                },
            )
        except Exception as e:
            logger.error(f"Search failed for '{index_name}': {e}", exc_info=True)
            raise VectorDatabaseError(
                f"Search failed: {e}",
                index_name=index_name,
                operation="search",
            )

    async def configure_reranker(
        self,
        index_name: str,
        enabled: bool,
        semantic_configuration_name: str | None = None,
    ) -> dict[str, Any]:
        """Enable or disable the semantic L2 reranker on an existing index."""
        try:
            index = await self._client_wrapper.index_client.get_index(index_name)
        except ResourceNotFoundError:
            raise IndexNotFoundError(index_name)

        # Parse existing description metadata
        metadata: dict[str, Any] = {}
        if index.description:
            try:
                metadata = json.loads(index.description)
            except json.JSONDecodeError:
                pass

        resolved_config_name = semantic_configuration_name or self._settings.semantic_configuration_name

        if enabled:
            semantic_search = SemanticSearch(
                configurations=[
                    SemanticConfiguration(
                        name=resolved_config_name,
                        prioritized_fields=SemanticPrioritizedFields(
                            title_field=SemanticField(field_name="content"),
                            content_fields=[SemanticField(field_name="content")],
                        ),
                    )
                ]
            )
            metadata["reranker_enabled"] = True
            metadata["semantic_configuration_name"] = resolved_config_name
        else:
            semantic_search = None
            metadata["reranker_enabled"] = False
            metadata["semantic_configuration_name"] = None

        updated_index = SearchIndex(
            name=index_name,
            fields=index.fields,
            vector_search=index.vector_search,
            semantic_search=semantic_search,
            description=json.dumps(metadata),
        )
        try:
            await self._client_wrapper.index_client.create_or_update_index(updated_index)
        except Exception as e:
            logger.error(f"Failed to configure reranker for '{index_name}': {e}", exc_info=True)
            raise VectorDatabaseError(
                f"Failed to configure reranker: {e}",
                index_name=index_name,
                operation="configure_reranker",
            )

        logger.info(
            f"Reranker {'enabled' if enabled else 'disabled'} for index '{index_name}' "
            f"(config: {resolved_config_name if enabled else 'n/a'})"
        )
        return {
            "index_name": index_name,
            "reranker_enabled": enabled,
            "semantic_configuration_name": resolved_config_name if enabled else None,
        }

    async def health_check(self) -> bool:
        """
        Check if the Azure AI Search service is accessible and healthy.

        Returns:
            True if service is accessible, False otherwise
        """
        try:
            # Try to list indexes - this is a lightweight operation
            indexes = self._client_wrapper.index_client.list_indexes()
            async for _ in indexes:  # Just check if we can iterate
                break
            logger.debug("Health check passed")
            return True
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False

    async def ensure_index(
        self, index_name: str, schema: dict[str, Any] | None = None
    ) -> bool:
        """
        Ensure that an index exists, creating it if necessary.

        Args:
            index_name: Name of the index
            schema: Optional schema for index creation

        Returns:
            True if index exists or was created successfully

        Raises:
            VectorDatabaseError: If index check or creation fails
        """
        try:
            # Try to get the index
            await self._client_wrapper.index_client.get_index(index_name)
            logger.debug(f"Index '{index_name}' already exists")
            return True
        except ResourceNotFoundError:
            # Index doesn't exist, create it
            logger.info(f"Index '{index_name}' not found, creating...")
            schema = schema or {"vector_dimension": 1536, "document_type": "operational"}
            if "document_type" not in schema:
                schema = {**schema, "document_type": "operational"}
            return await self.create_index(index_name, schema)
        except Exception as e:
            logger.error(f"Failed to ensure index '{index_name}': {e}", exc_info=True)
            raise VectorDatabaseError(
                f"Failed to ensure index: {e}",
                index_name=index_name,
                operation="ensure_index",
            )

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
        try:
            client = self._client_wrapper.get_search_client(index_name)

            # Use search with count=True to get total count
            results = await client.search(search_text="*", include_total_count=True, top=0)

            # Get the total count from results
            count = await results.get_count() if hasattr(results, "get_count") else 0

            logger.debug(f"Index '{index_name}' contains {count} documents")
            return count

        except HttpResponseError as e:
            if e.status_code == 404:
                raise IndexNotFoundError(index_name)
            raise VectorDatabaseError(
                f"Failed to get document count: {e}",
                index_name=index_name,
                operation="get_document_count",
            )
        except Exception as e:
            logger.error(
                f"Failed to get document count for '{index_name}': {e}", exc_info=True
            )
            raise VectorDatabaseError(
                f"Failed to get document count: {e}",
                index_name=index_name,
                operation="get_document_count",
            )

    async def list_indexes(self) -> list[dict[str, Any]]:
        """
        List all indexes/collections.

        Returns:
            List of index metadata dictionaries

        Raises:
            VectorDatabaseError: If operation fails
        """
        try:
            logger.debug("Listing all indexes")
            indexes = []

            # List all indexes
            async for index in self._client_wrapper.index_client.list_indexes():
                # Extract vector dimension from the contentVector field
                vector_dimension: int | None = None
                for field in index.fields:
                    if field.name == "contentVector" and hasattr(
                        field, "vector_search_dimensions"
                    ):
                        vector_dimension = field.vector_search_dimensions
                        break

                # Extract metadata from description JSON
                embedding_model: str | None = None
                document_type: str | None = None
                reranker_enabled: bool = False
                semantic_configuration_name: str | None = None
                if index.description:
                    try:
                        meta = json.loads(index.description)
                        embedding_model = meta.get("embedding_model")
                        document_type = meta.get("document_type")
                        reranker_enabled = bool(meta.get("reranker_enabled", False))
                        semantic_configuration_name = meta.get("semantic_configuration_name")
                    except json.JSONDecodeError:
                        pass

                # Get document count (may be slow for large indexes)
                try:
                    doc_count = await self.get_document_count(index.name)
                except Exception as e:
                    logger.warning(
                        f"Could not get document count for index '{index.name}': {e}"
                    )
                    doc_count = 0

                indexes.append(
                    {
                        "name": index.name,
                        "vector_dimension": vector_dimension,
                        "embedding_model": embedding_model,
                        "document_type": document_type,
                        "reranker_enabled": reranker_enabled,
                        "semantic_configuration_name": semantic_configuration_name,
                        "document_count": doc_count,
                    }
                )

            logger.info(f"Listed {len(indexes)} indexes")
            return indexes

        except Exception as e:
            logger.error(f"Failed to list indexes: {e}", exc_info=True)
            raise VectorDatabaseError(
                f"Failed to list indexes: {e}",
                operation="list_indexes",
            )

    async def get_index(self, index_name: str) -> dict[str, Any]:
        """
        Get detailed information about an index.

        Args:
            index_name: Name of the index

        Returns:
            Index metadata dictionary

        Raises:
            IndexNotFoundError: If index doesn't exist
            VectorDatabaseError: If operation fails
        """
        try:
            logger.debug(f"Getting index details for '{index_name}'")

            # Get the index
            index = await self._client_wrapper.index_client.get_index(index_name)

            # Extract vector dimension
            vector_dimension: int | None = None
            for field in index.fields:
                if field.name == "contentVector" and hasattr(
                    field, "vector_search_dimensions"
                ):
                    vector_dimension = field.vector_search_dimensions
                    break

            # Extract metadata from description JSON
            embedding_model: str | None = None
            document_type: str | None = None
            reranker_enabled: bool = False
            semantic_configuration_name: str | None = None
            if index.description:
                try:
                    meta = json.loads(index.description)
                    embedding_model = meta.get("embedding_model")
                    document_type = meta.get("document_type")
                    reranker_enabled = bool(meta.get("reranker_enabled", False))
                    semantic_configuration_name = meta.get("semantic_configuration_name")
                except json.JSONDecodeError:
                    pass

            # Get document count
            doc_count = await self.get_document_count(index_name)

            # Build field schema
            field_names = [field.name for field in index.fields]

            result = {
                "name": index.name,
                "vector_dimension": vector_dimension,
                "embedding_model": embedding_model,
                "document_type": document_type,
                "reranker_enabled": reranker_enabled,
                "semantic_configuration_name": semantic_configuration_name,
                "document_count": doc_count,
                "schema": {
                    "fields": field_names,
                },
            }

            logger.info(f"Retrieved index details for '{index_name}'")
            return result

        except ResourceNotFoundError:
            logger.warning(f"Index '{index_name}' not found")
            raise IndexNotFoundError(index_name)
        except IndexNotFoundError:
            raise
        except Exception as e:
            logger.error(
                f"Failed to get index '{index_name}': {e}",
                exc_info=True,
            )
            raise VectorDatabaseError(
                f"Failed to get index: {e}",
                index_name=index_name,
                operation="get_index",
            )

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
        """
        try:
            logger.info(f"Deleting index '{index_name}'")

            # Check if index exists first
            try:
                await self._client_wrapper.index_client.get_index(index_name)
            except ResourceNotFoundError:
                logger.warning(f"Index '{index_name}' not found")
                raise IndexNotFoundError(index_name)

            # Delete the index
            await self._client_wrapper.index_client.delete_index(index_name)

            logger.info(f"Successfully deleted index '{index_name}'")
            return True

        except IndexNotFoundError:
            raise
        except Exception as e:
            logger.error(
                f"Failed to delete index '{index_name}': {e}",
                exc_info=True,
            )
            raise VectorDatabaseError(
                f"Failed to delete index: {e}",
                index_name=index_name,
                operation="delete_index",
            )

    async def close(self) -> None:
        """Close all connections and release resources."""
        logger.debug("Closing AzureAISearchAdapter...")
        await self._client_wrapper.close()
        logger.debug("AzureAISearchAdapter closed")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - ensures connections are closed."""
        await self.close()
        return False  # Don't suppress exceptions

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"AzureAISearchAdapter(endpoint={self._settings.endpoint})"
