"""Dependency injection container for the application.

This module defines the application's dependency injection container using
the dependency-injector library. It provides:

- Thread-safe singleton providers for all infrastructure clients, adapters,
  repositories, and use cases
- Automatic wiring to HTTP routes and queue triggers
- Resource lifecycle management with proper cleanup
- Support for test provider overriding
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from dependency_injector import containers, providers

from src.application.use_cases.chunk_document import ChunkDocumentUseCase
from src.application.use_cases.chunk_document_and_enqueue_vectorization import (
    ChunkDocumentAndEnqueueVectorizationUseCase,
)
from src.application.use_cases.delete_document import DeleteDocumentUseCase
from src.application.use_cases.ingest_documents import IngestDocumentsUseCase
from src.application.use_cases.list_chunks import ListChunksUseCase
from src.application.use_cases.list_documents import ListDocumentsUseCase
from src.application.use_cases.manage_collection import ManageCollectionUseCase
from src.application.use_cases.process_document import ProcessDocumentUseCase
from src.application.use_cases.process_text_and_enqueue_chunking import (
    ProcessTextAndEnqueueChunkingUseCase,
)
from src.application.use_cases.semantic_search import SemanticSearchUseCase
from src.application.use_cases.update_metadata import UpdateMetadataUseCase
from src.application.use_cases.upload_and_enqueue_document import (
    UploadAndEnqueueDocumentUseCase,
)
from src.application.use_cases.upload_document import UploadDocumentUseCase
from src.application.use_cases.vectorize_chunks import VectorizeChunksUseCase
from src.application.use_cases.vectorize_chunks_and_enqueue_ingestion import (
    VectorizeChunksAndEnqueueIngestionUseCase,
)
from src.config.settings import Settings, get_settings
from src.infrastructure.azure.adapters.blob_store_adapter import BlobStoreAdapter
from src.infrastructure.azure.adapters.document_intelligence_azure import (
    AzureDocumentIntelligenceAdapter,
)
from src.infrastructure.azure.adapters.document_intelligence_fake import (
    FakeDocumentIntelligenceAdapter,
)
from src.infrastructure.azure.adapters.embedding_azure_openai import AzureOpenAIEmbeddings
from src.infrastructure.azure.adapters.embedding_fake import FakeEmbeddings
from src.infrastructure.azure.adapters.queue_publisher_azure import AzureQueuePublisher
from src.infrastructure.azure.adapters.vector_search_azure import AzureAISearchAdapter
from src.infrastructure.azure.clients.blob_client import BlobStorageClient
from src.infrastructure.azure.clients.queue_client import QueueStorageClient
from src.infrastructure.chonkie.chunker_chonkie import ChonkieChunker
from src.infrastructure.llamaindex.chunker_fake import FakeChunker
from src.infrastructure.llamaindex.chunker_llamaindex import LlamaIndexChunker

if TYPE_CHECKING:
    from src.application.ports.chunker import ChunkerPort
    from src.application.ports.document_intelligence import DocumentIntelligencePort
    from src.application.ports.embedding import EmbeddingPort

logger = logging.getLogger(__name__)


def _create_document_intelligence_adapter(settings: Settings) -> "DocumentIntelligencePort":
    """Create appropriate document intelligence adapter based on configuration.

    Returns FakeDocumentIntelligenceAdapter for local development (use_fake=True),
    or AzureDocumentIntelligenceAdapter for production when configured.

    Args:
        settings: Application settings

    Returns:
        DocumentIntelligencePort implementation
    """
    di_settings = settings.document_intelligence

    # Use fake adapter if explicitly requested
    if di_settings.use_fake:
        logger.info("Using FakeDocumentIntelligenceAdapter for document processing")
        return FakeDocumentIntelligenceAdapter(
            simulated_delay_seconds=di_settings.simulated_delay_seconds,
        )

    # Use Azure adapter if credentials are configured
    if di_settings.is_configured:
        logger.info(
            f"Using AzureDocumentIntelligenceAdapter for document processing "
            f"(endpoint: {di_settings.endpoint[:30]}...)"
        )
        return AzureDocumentIntelligenceAdapter(settings=di_settings)

    # Fall back to fake adapter if Azure is not configured
    logger.warning(
        "Azure Document Intelligence not configured (missing endpoint or api_key), "
        "falling back to fake adapter. Set DOCUMENT_INTELLIGENCE_ENDPOINT and "
        "DOCUMENT_INTELLIGENCE_API_KEY environment variables for production use."
    )
    return FakeDocumentIntelligenceAdapter(
        simulated_delay_seconds=di_settings.simulated_delay_seconds,
    )


def _create_chunker_adapter(settings: Settings) -> "ChunkerPort":
    """Create appropriate chunker adapter based on configuration.

    Returns FakeChunker for local development (use_fake=True),
    ChonkieChunker when adapter='chonkie', or LlamaIndexChunker otherwise.

    Args:
        settings: Application settings

    Returns:
        ChunkerPort implementation
    """
    chunking_settings = settings.chunking

    # Use fake adapter if explicitly requested
    if chunking_settings.use_fake:
        logger.info("Using FakeChunker for document chunking")
        return FakeChunker(simulated_delay_seconds=0.0)

    # Route to the configured adapter
    if chunking_settings.adapter == "chonkie":
        logger.info("Using ChonkieChunker for structure-aware document chunking")
        return ChonkieChunker(settings=chunking_settings)

    # Default: LlamaIndex adapter
    logger.info("Using LlamaIndexChunker for document chunking")
    return LlamaIndexChunker(settings=chunking_settings)


def _create_embedding_adapter(settings: Settings) -> "EmbeddingPort":
    """Create appropriate embedding adapter based on configuration.

    Returns FakeEmbeddings for local development (use_fake=True),
    or AzureOpenAIEmbeddings for production when configured.

    Args:
        settings: Application settings

    Returns:
        EmbeddingPort implementation
    """
    embedding_settings = settings.embedding

    # Use fake adapter if explicitly requested
    if embedding_settings.use_fake:
        logger.info("Using FakeEmbeddings for vectorization")
        return FakeEmbeddings(
            simulated_delay_seconds=0.1,
            default_model=embedding_settings.default_model,
        )

    # Use Azure OpenAI adapter if credentials are configured
    if embedding_settings.is_configured:
        logger.info(
            f"Using AzureOpenAIEmbeddings for vectorization "
            f"(endpoint: {embedding_settings.endpoint[:30]}...)"
        )
        return AzureOpenAIEmbeddings(settings=embedding_settings)

    # Fall back to fake adapter if Azure OpenAI is not configured
    logger.warning(
        "Azure OpenAI not configured (missing endpoint, api_key, or deployment_name), "
        "falling back to fake adapter. Set EMBEDDING_ENDPOINT, EMBEDDING_API_KEY, "
        "and EMBEDDING_DEPLOYMENT_NAME environment variables for production use."
    )
    return FakeEmbeddings(
        simulated_delay_seconds=0.1,
        default_model=embedding_settings.default_model,
    )


def _create_document_repository(settings: Settings, session_factory=None):
    """Create SQL Server document repository (implements DocumentStorePort, PipelineStorePort, DocumentQueryPort)."""
    if not settings.sql_server.enabled or session_factory is None:
        raise RuntimeError(
            "SQL Server metadata store is required. Set SQL_SERVER_ENABLED=true and configure SQL_SERVER_DATABASE_URL."
        )

    from src.infrastructure.sqlserver.repositories.document_repository import (
        DocumentRepositorySQLServer,
    )

    logger.info("Using SQL Server DocumentRepository")
    return DocumentRepositorySQLServer(session_factory=session_factory)


def _create_chunk_index_repository(settings: Settings, session_factory=None):
    """Create SQL Server chunk index repository."""
    if not settings.sql_server.enabled or session_factory is None:
        raise RuntimeError(
            "SQL Server metadata store is required. Set SQL_SERVER_ENABLED=true and configure SQL_SERVER_DATABASE_URL."
        )

    from src.infrastructure.sqlserver.repositories.chunk_index_repository import (
        ChunkIndexRepositorySQLServer,
    )

    logger.info("Using SQL Server ChunkIndexRepository")
    return ChunkIndexRepositorySQLServer(session_factory=session_factory)


def _create_processing_events_repository(settings: Settings, session_factory=None):
    """Create processing events repository (SQL Server only, None when disabled)."""
    if settings.sql_server.enabled and session_factory is not None:
        from src.infrastructure.sqlserver.repositories.processing_events_repository import (
            ProcessingEventsRepositorySQLServer,
        )

        logger.info("Using SQL Server ProcessingEventsRepository")
        return ProcessingEventsRepositorySQLServer(session_factory=session_factory)

    return None


def _create_jwks_client(jwks_uri: str, ttl_seconds: int):
    """Lazy-import JwksClient to avoid circular imports with auth.dependencies."""
    from src.presentation.http.auth.jwks_client import JwksClient

    return JwksClient(jwks_uri=jwks_uri, ttl_seconds=ttl_seconds)


def _create_token_validator(jwks_client, settings):
    """Lazy-import TokenValidator to avoid circular imports with auth.dependencies."""
    from src.presentation.http.auth.token_validator import TokenValidator

    return TokenValidator(jwks_client=jwks_client, settings=settings)


def _create_sql_session_factory(settings: Settings):
    """Create SQL Server async session factory (None when disabled)."""
    if not settings.sql_server.enabled or not settings.sql_server.is_configured:
        return None

    from src.infrastructure.sqlserver.database import create_engine, create_session_factory

    engine = create_engine(settings.sql_server)
    logger.info("SQL Server async engine created")
    return create_session_factory(engine)


class Container(containers.DeclarativeContainer):
    """Application dependency injection container.

    This container manages all singletons for:
    - Infrastructure clients (blob storage, queue storage)
    - Adapters (document intelligence, embedding, vector database, chunker)
    - Repositories (document, chunk index)
    - Use cases (all business logic operations)

    Attributes:
        wiring_config: Configuration for automatic injection into modules
    """

    wiring_config = containers.WiringConfiguration(
        modules=[
            # Auth
            "src.presentation.http.auth.dependencies",
            # HTTP routes
            "src.presentation.http.routes.capabilities",
            "src.presentation.http.routes.chunking",
            "src.presentation.http.routes.collections",
            "src.presentation.http.routes.contents",
            "src.presentation.http.routes.document_management",
            "src.presentation.http.routes.document_upload_operational",
            "src.presentation.http.routes.document_upload_publication",
            "src.presentation.http.routes.search",
            "src.presentation.http.routes.search_operational",
            "src.presentation.http.routes.search_publication",
            "src.presentation.http.routes.vectorization",
            "src.presentation.http.routes.analytics",
            # Queue triggers
            "src.presentation.queue.triggers.chunk_document_trigger",
            "src.presentation.queue.triggers.ingest_into_db_trigger",
            "src.presentation.queue.triggers.process_text_trigger",
            "src.presentation.queue.triggers.vectorize_chunks_trigger",
        ]
    )

    # ========== Configuration ==========

    settings = providers.Singleton(get_settings)

    # ========== Auth ==========

    jwks_client = providers.Singleton(
        _create_jwks_client,
        jwks_uri=settings.provided.entra_id.effective_jwks_uri,
        ttl_seconds=settings.provided.entra_id.jwks_cache_ttl_seconds,
    )

    token_validator = providers.Singleton(
        _create_token_validator,
        jwks_client=jwks_client,
        settings=settings.provided.entra_id,
    )

    # ========== Infrastructure Clients ==========

    blob_storage_client = providers.Singleton(
        BlobStorageClient,
        settings=settings.provided.azure_storage,
    )

    queue_storage_client = providers.Singleton(
        QueueStorageClient,
        settings=settings.provided.azure_storage,
    )

    # ========== Adapters (Conditional Creation via Factories) ==========

    document_intelligence_adapter = providers.Singleton(
        _create_document_intelligence_adapter,
        settings=settings,
    )

    chunker_adapter = providers.Singleton(
        _create_chunker_adapter,
        settings=settings,
    )

    embedding_adapter = providers.Singleton(
        _create_embedding_adapter,
        settings=settings,
    )

    vector_database_adapter = providers.Singleton(
        AzureAISearchAdapter,
        settings=settings.provided.vector_search,
    )

    queue_publisher = providers.Singleton(
        AzureQueuePublisher,
        queue_client=queue_storage_client,
    )

    blob_store_adapter = providers.Singleton(
        BlobStoreAdapter,
        blob_client=blob_storage_client,
        settings=settings.provided.azure_storage,
    )

    # ========== SQL Server (conditional) ==========

    sql_session_factory = providers.Singleton(
        _create_sql_session_factory,
        settings=settings,
    )

    # ========== Repositories ==========

    document_repository = providers.Singleton(
        _create_document_repository,
        settings=settings,
        session_factory=sql_session_factory,
    )

    chunk_index_repository = providers.Singleton(
        _create_chunk_index_repository,
        settings=settings,
        session_factory=sql_session_factory,
    )

    processing_events_repository = providers.Singleton(
        _create_processing_events_repository,
        settings=settings,
        session_factory=sql_session_factory,
    )

    # ========== Use Cases ==========

    process_document_use_case = providers.Singleton(
        ProcessDocumentUseCase,
        blob_client=blob_store_adapter,
        document_intelligence=document_intelligence_adapter,
        pipeline_store=document_repository,
        processing_events=processing_events_repository,
    )

    process_text_and_enqueue_chunking_use_case = providers.Singleton(
        ProcessTextAndEnqueueChunkingUseCase,
        process_use_case=process_document_use_case,
        queue_publisher=queue_publisher,
        queue_name=settings.provided.azure_storage.queue_text_to_chunks,
        pipeline_store=document_repository,
        chunk_output_container=settings.provided.azure_storage.container_chunks,
    )

    chunk_document_use_case = providers.Singleton(
        ChunkDocumentUseCase,
        blob_client=blob_store_adapter,
        chunker=chunker_adapter,
        chunk_index_repository=chunk_index_repository,
        pipeline_store=document_repository,
        processing_events=processing_events_repository,
    )

    list_chunks_use_case = providers.Singleton(
        ListChunksUseCase,
        chunk_index_store=chunk_index_repository,
        file_index_store=document_repository,
    )

    chunk_document_and_enqueue_vectorization_use_case = providers.Singleton(
        ChunkDocumentAndEnqueueVectorizationUseCase,
        chunk_use_case=chunk_document_use_case,
        queue_publisher=queue_publisher,
        queue_name=settings.provided.azure_storage.queue_chunk_to_vector,
        pipeline_store=document_repository,
        embedding_output_container=settings.provided.azure_storage.container_embeddings,
        embedding_model=settings.provided.embedding.default_model,
        embedding_batch_size=providers.Factory(
            lambda settings: min(settings.embedding.max_batch_size, 100),
            settings=settings,
        ),
    )

    vectorize_chunks_use_case = providers.Singleton(
        VectorizeChunksUseCase,
        blob_client=blob_store_adapter,
        embedding_port=embedding_adapter,
        chunk_index_repository=chunk_index_repository,
        pipeline_store=document_repository,
        processing_events=processing_events_repository,
    )

    vectorize_chunks_and_enqueue_ingestion_use_case = providers.Singleton(
        VectorizeChunksAndEnqueueIngestionUseCase,
        vectorize_use_case=vectorize_chunks_use_case,
        queue_publisher=queue_publisher,
        queue_name=settings.provided.azure_storage.queue_ingest_to_db,
        pipeline_store=document_repository,
        batch_size=100,
    )

    semantic_search_use_case = providers.Singleton(
        SemanticSearchUseCase,
        vector_database=vector_database_adapter,
        embedding_port=embedding_adapter,
    )

    manage_collection_use_case = providers.Singleton(
        ManageCollectionUseCase,
        vector_database=vector_database_adapter,
    )

    ingest_documents_use_case = providers.Singleton(
        IngestDocumentsUseCase,
        vector_database=vector_database_adapter,
        document_store=document_repository,
        processing_events=processing_events_repository,
    )

    # ========== Document Management Use Cases ==========

    upload_document_use_case = providers.Singleton(
        UploadDocumentUseCase,
        blob_store=blob_store_adapter,
        metadata_store=document_repository,
        container_name=settings.provided.azure_storage.container_raw,
        allowed_types=settings.provided.file_upload.allowed_mime_types,
        max_size_bytes=settings.provided.file_upload.max_file_size_bytes,
    )

    upload_and_enqueue_document_use_case = providers.Singleton(
        UploadAndEnqueueDocumentUseCase,
        upload_use_case=upload_document_use_case,
        queue_publisher=queue_publisher,
        queue_name=settings.provided.azure_storage.queue_raw_to_text,
    )

    update_metadata_use_case = providers.Singleton(
        UpdateMetadataUseCase,
        metadata_store=document_repository,
        vector_database=vector_database_adapter,
        index_name=settings.provided.vector_search.default_index_name,
    )

    delete_document_use_case = providers.Singleton(
        DeleteDocumentUseCase,
        blob_store=blob_store_adapter,
        metadata_store=document_repository,
        vector_database=vector_database_adapter,
        container_raw=settings.provided.azure_storage.container_raw,
        container_text=settings.provided.azure_storage.container_text,
        container_chunks=settings.provided.azure_storage.container_chunks,
        container_embeddings=settings.provided.azure_storage.container_embeddings,
        index_name=settings.provided.vector_search.default_index_name,
    )

    list_documents_use_case = providers.Singleton(
        ListDocumentsUseCase,
        metadata_store=document_repository,
    )

    async def shutdown_resources(self) -> None:
        """Close all resources that need cleanup.

        This method is called during application shutdown to properly close
        all resources like database connections, API clients, and file handles.
        Resources are closed in reverse order of dependencies to avoid issues.

        Resources that may have close methods:
        - Adapters (API clients)
        - Repositories (database connections)
        - Storage clients (cloud connections)
        """

        async def _maybe_close(resource: object) -> None:
            """Close a resource if it has a close method."""
            close_fn = getattr(resource, "close", None)
            if not callable(close_fn):
                return
            try:
                result = close_fn()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.exception(f"Error closing resource {resource}: {e}")

        # Dispose SQL Server engine if it was created
        try:
            session_factory = self.sql_session_factory()
            if session_factory is not None:
                engine = session_factory.kw.get("bind")
                if engine is not None:
                    await engine.dispose()
                    logger.info("SQL Server engine disposed")
        except Exception:
            pass

        # Only close resources that own connections/state
        # Use cases are stateless and don't need closing
        resources_to_close = [
            # Auth
            self.jwks_client,
            # Adapters (may have API connections)
            self.vector_database_adapter,
            self.embedding_adapter,
            self.chunker_adapter,
            self.document_intelligence_adapter,
            # Repositories (may have database connections)
            self.chunk_index_repository,
            self.document_repository,
            # Infrastructure clients (own connections)
            self.queue_publisher,
            self.queue_storage_client,
            self.blob_storage_client,
        ]

        for provider in resources_to_close:
            try:
                instance = provider()  # Get singleton instance if created
                if instance is not None:
                    await _maybe_close(instance)
            except Exception:
                # Provider not yet instantiated, skip
                pass

        # Reset all singletons for clean shutdown
        self.reset_singletons()
        logger.info("All resources closed successfully")
