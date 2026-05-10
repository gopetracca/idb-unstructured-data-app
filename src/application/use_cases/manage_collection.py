"""Use case for managing vector database collections."""

import logging
from datetime import datetime

from src.application.dto.collection_dto import (
    ConfigureRerankerInput,
    ConfigureRerankerOutput,
    CreateCollectionInput,
    CreateCollectionOutput,
    DeleteCollectionInput,
    DeleteCollectionOutput,
    GetCollectionInput,
    GetCollectionOutput,
    ListCollectionsOutput,
    CollectionInfo,
)
from src.application.ports.vector_database import VectorDatabasePort
from src.core.errors import IndexAlreadyExistsError, IndexNotFoundError

logger = logging.getLogger(__name__)


class ManageCollectionUseCase:
    """
    Use case for managing vector database collections (indexes).

    Provides operations to create, list, retrieve, and delete collections
    in the vector database.
    """

    def __init__(self, vector_database: VectorDatabasePort):
        """
        Initialize the ManageCollectionUseCase.

        Args:
            vector_database: Vector database port implementation
        """
        self._vector_db = vector_database

    async def create_collection(
        self, input_dto: CreateCollectionInput
    ) -> CreateCollectionOutput:
        """
        Create a new collection with specified configuration.

        Args:
            input_dto: Collection creation parameters

        Returns:
            CreateCollectionOutput with creation result

        Raises:
            IndexAlreadyExistsError: If collection already exists
            VectorDatabaseError: If creation fails
        """
        logger.info(
            f"Creating collection '{input_dto.name}' with dimension {input_dto.vector_dimension}, "
            f"embedding_model='{input_dto.embedding_model}', "
            f"correlation_id={input_dto.correlation_id}"
        )

        try:
            # Create the index with specified schema
            schema = {
                "vector_dimension": input_dto.vector_dimension,
                "embedding_model": input_dto.embedding_model,
                "document_type": input_dto.document_type,
            }
            await self._vector_db.create_index(input_dto.name, schema)

            # Return success response
            return CreateCollectionOutput(
                name=input_dto.name,
                vector_dimension=input_dto.vector_dimension,
                embedding_model=input_dto.embedding_model,
                status="created",
                created_at=datetime.utcnow(),
                correlation_id=input_dto.correlation_id,
            )

        except IndexAlreadyExistsError:
            logger.warning(
                f"Collection '{input_dto.name}' already exists, "
                f"correlation_id={input_dto.correlation_id}"
            )
            raise

        except Exception as e:
            logger.error(
                f"Failed to create collection '{input_dto.name}': {e}, "
                f"correlation_id={input_dto.correlation_id}"
            )
            raise

    async def list_collections(self, tenant_id: str, correlation_id: str) -> ListCollectionsOutput:
        """
        List all collections for a tenant.

        Args:
            tenant_id: Tenant identifier
            correlation_id: Correlation ID for tracing

        Returns:
            ListCollectionsOutput with collection list

        Raises:
            VectorDatabaseError: If listing fails
        """
        logger.info(
            f"Listing collections for tenant '{tenant_id}', "
            f"correlation_id={correlation_id}"
        )

        try:
            # Get all indexes
            indexes = await self._vector_db.list_indexes()

            # Transform to CollectionInfo DTOs
            collections = [
                CollectionInfo(
                    name=index["name"],
                    vector_dimension=index.get("vector_dimension"),
                    embedding_model=index.get("embedding_model"),
                    document_count=index.get("document_count", 0),
                    created_at=index.get("created_at"),
                )
                for index in indexes
            ]

            logger.info(
                f"Found {len(collections)} collections, "
                f"correlation_id={correlation_id}"
            )

            return ListCollectionsOutput(
                collections=collections,
                total_count=len(collections),
                correlation_id=correlation_id,
            )

        except Exception as e:
            logger.error(
                f"Failed to list collections: {e}, "
                f"correlation_id={correlation_id}"
            )
            raise

    async def get_collection(
        self, input_dto: GetCollectionInput
    ) -> GetCollectionOutput:
        """
        Get detailed information about a specific collection.

        Args:
            input_dto: Collection retrieval parameters

        Returns:
            GetCollectionOutput with collection details

        Raises:
            IndexNotFoundError: If collection doesn't exist
            VectorDatabaseError: If retrieval fails
        """
        logger.info(
            f"Getting collection details for '{input_dto.collection_name}', "
            f"correlation_id={input_dto.correlation_id}"
        )

        try:
            # Get index details
            index_info = await self._vector_db.get_index(input_dto.collection_name)

            return GetCollectionOutput(
                name=index_info["name"],
                vector_dimension=index_info.get("vector_dimension"),
                embedding_model=index_info.get("embedding_model"),
                document_count=index_info["document_count"],
                index_schema=index_info["schema"],
                created_at=index_info.get("created_at"),
                last_updated=index_info.get("last_updated"),
                correlation_id=input_dto.correlation_id,
            )

        except IndexNotFoundError:
            logger.warning(
                f"Collection '{input_dto.collection_name}' not found, "
                f"correlation_id={input_dto.correlation_id}"
            )
            raise

        except Exception as e:
            logger.error(
                f"Failed to get collection '{input_dto.collection_name}': {e}, "
                f"correlation_id={input_dto.correlation_id}"
            )
            raise

    async def configure_reranker(
        self, input_dto: ConfigureRerankerInput
    ) -> ConfigureRerankerOutput:
        """
        Enable or disable the semantic L2 reranker on a collection.

        Args:
            input_dto: Reranker configuration parameters

        Returns:
            ConfigureRerankerOutput with the updated state

        Raises:
            IndexNotFoundError: If collection doesn't exist
            VectorDatabaseError: If the operation fails
        """
        logger.info(
            f"Configuring reranker for '{input_dto.collection_name}': "
            f"enabled={input_dto.enabled}, "
            f"semantic_config={input_dto.semantic_configuration_name!r}, "
            f"correlation_id={input_dto.correlation_id}"
        )

        try:
            result = await self._vector_db.configure_reranker(
                index_name=input_dto.collection_name,
                enabled=input_dto.enabled,
                semantic_configuration_name=input_dto.semantic_configuration_name,
            )
            return ConfigureRerankerOutput(
                collection_name=input_dto.collection_name,
                reranker_enabled=result["reranker_enabled"],
                semantic_configuration_name=result["semantic_configuration_name"],
                correlation_id=input_dto.correlation_id,
            )

        except IndexNotFoundError:
            logger.warning(
                f"Collection '{input_dto.collection_name}' not found, "
                f"correlation_id={input_dto.correlation_id}"
            )
            raise

        except Exception as e:
            logger.error(
                f"Failed to configure reranker for '{input_dto.collection_name}': {e}, "
                f"correlation_id={input_dto.correlation_id}"
            )
            raise

    async def delete_collection(
        self, input_dto: DeleteCollectionInput
    ) -> DeleteCollectionOutput:
        """
        Delete a collection and all its documents.

        Args:
            input_dto: Collection deletion parameters

        Returns:
            DeleteCollectionOutput with deletion result

        Raises:
            IndexNotFoundError: If collection doesn't exist
            VectorDatabaseError: If deletion fails
        """
        logger.info(
            f"Deleting collection '{input_dto.collection_name}', "
            f"correlation_id={input_dto.correlation_id}"
        )

        try:
            # Get document count before deletion
            try:
                doc_count = await self._vector_db.get_document_count(
                    input_dto.collection_name
                )
            except Exception:
                # If we can't get count, default to 0
                doc_count = 0

            # Delete the index
            await self._vector_db.delete_index(input_dto.collection_name)

            logger.info(
                f"Successfully deleted collection '{input_dto.collection_name}' "
                f"with {doc_count} documents, "
                f"correlation_id={input_dto.correlation_id}"
            )

            return DeleteCollectionOutput(
                name=input_dto.collection_name,
                status="deleted",
                documents_deleted=doc_count,
                correlation_id=input_dto.correlation_id,
            )

        except IndexNotFoundError:
            logger.warning(
                f"Collection '{input_dto.collection_name}' not found, "
                f"correlation_id={input_dto.correlation_id}"
            )
            raise

        except Exception as e:
            logger.error(
                f"Failed to delete collection '{input_dto.collection_name}': {e}, "
                f"correlation_id={input_dto.correlation_id}"
            )
            raise
