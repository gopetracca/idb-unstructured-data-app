"""Shared pytest fixtures for all tests."""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dotenv import load_dotenv

# Register testcontainers session-scoped fixtures so they are available to all
# integration tests without needing explicit imports in each conftest.
pytest_plugins = [
    "tests.testcontainers_fixtures",
    # "tests.integration.infrastructure.sqlserver_entity_factories",
]

# Load .env file before any other imports
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    load_dotenv(env_file)

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config.settings import AzureStorageSettings
from src.container import Container
from src.core.entities.chunk_index import ChunkIndex
from src.core.entities.composites import DocumentComplete, DocumentWithPipeline
from src.core.entities.document import Document
from src.core.entities.document_analysis import (
    ExtractionMetadata,
    MarkdownOutput,
    PageContent,
)
from src.core.entities.file_index import FileIndex
from src.core.entities.pipeline_state import OverallStatus, PipelineState, ProcessingStage
from src.core.value_objects.document_metadata import DocumentMetadata
from src.infrastructure.azure.adapters.document_intelligence_fake import (
    FakeDocumentIntelligenceAdapter,
)


# ============================================================================
# Settings Fixtures
# ============================================================================


@pytest.fixture
def azure_storage_settings() -> AzureStorageSettings:
    """Create Azure Storage settings for testing."""
    return AzureStorageSettings(
        connection_string="UseDevelopmentStorage=true",
        container_raw="test-raw",
        container_text="test-text",
        container_chunks="test-chunks",
        container_embeddings="test-embeddings",
        queue_raw_file="test-raw-file",
        queue_raw_to_text="test-process-text",
        queue_text_to_chunks="test-chunk-document",
        queue_chunk_to_vector="test-vectorize-chunks",
        queue_ingest_to_db="test-ingest-to-db",
        queue_delete_file="test-delete-file",
    )


@pytest.fixture
def azurite_connection_string() -> str:
    """Get Azurite connection string from environment or use default."""
    return os.getenv(
        "AZURE_STORAGE_CONNECTION_STRING",
        "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
        "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/"
        "K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
        "QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;"
        "TableEndpoint=http://127.0.0.1:10002/devstoreaccount1",
    )


# ============================================================================
# Entity Fixtures
# ============================================================================


@pytest.fixture
def sample_tenant_id() -> str:
    """Generate a sample tenant ID."""
    return "tenant-001"


@pytest.fixture
def sample_file_id() -> str:
    """Generate a sample file ID."""
    return str(uuid4())


@pytest.fixture
def sample_chunk_id() -> str:
    """Generate a sample chunk ID."""
    return str(uuid4())


@pytest.fixture
def sample_file_index(sample_tenant_id: str, sample_file_id: str) -> FileIndex:
    """Create a sample FileIndex entity."""
    return FileIndex(
        tenant_id=sample_tenant_id,
        file_id=sample_file_id,
        blob_name="test-document.pdf",
        content_type="application/pdf",
        size_bytes=1024000,
        content_hash="sha256:abc123",
        upload_timestamp=datetime.now(timezone.utc),
        file_version=1,
        current_stage=ProcessingStage.DISPATCHER,
        overall_status=OverallStatus.QUEUED,
        chunk_count=0,
        embedded_chunk_count=0,
        chunking_strategy="recursive",
        embedding_model="text-embedding-ada-002",
        vector_db_targets='["azure-ai-search"]',
        collection_name="test-collection",
        # Blob storage references (SSOT for content location)
        raw_blob_ref=f"{sample_tenant_id}/{sample_file_id}/test-document.pdf",
        text_blob_ref=f"{sample_tenant_id}/{sample_file_id}/text.json",
        # Promoted metadata fields
        document_type="operational",
        language="en",
    )


@pytest.fixture
def sample_document(sample_tenant_id: str, sample_file_id: str) -> Document:
    """Create a sample Document entity."""
    return Document(
        tenant_id=sample_tenant_id,
        file_id=sample_file_id,
        blob_name="test-document.pdf",
        content_type="application/pdf",
        size_bytes=1024000,
        content_hash="sha256:abc123",
        upload_timestamp=datetime.now(timezone.utc),
        file_version=1,
        raw_blob_ref=f"{sample_tenant_id}/{sample_file_id}/test-document.pdf",
        text_blob_ref=f"{sample_tenant_id}/{sample_file_id}/text.json",
        collection_name="test-collection",
    )


@pytest.fixture
def sample_pipeline_state(sample_file_id: str) -> PipelineState:
    """Create a sample PipelineState entity."""
    return PipelineState(
        file_id=sample_file_id,
        current_stage=ProcessingStage.DISPATCHER,
        overall_status=OverallStatus.QUEUED,
        chunk_count=0,
        embedded_chunk_count=0,
        chunking_strategy="recursive",
        embedding_model="text-embedding-ada-002",
        vector_db_targets='["azure-ai-search"]',
    )


@pytest.fixture
def sample_document_metadata(sample_file_id: str) -> DocumentMetadata:
    """Create a sample DocumentMetadata entity."""
    return DocumentMetadata(
        file_id=sample_file_id,
        document_type="operational",
        language="en",
    )


@pytest.fixture
def sample_document_with_pipeline(
    sample_document: Document, sample_pipeline_state: PipelineState
) -> DocumentWithPipeline:
    """Create a sample DocumentWithPipeline composite."""
    return DocumentWithPipeline(
        document=sample_document,
        pipeline=sample_pipeline_state,
    )


@pytest.fixture
def sample_document_complete(
    sample_document: Document,
    sample_pipeline_state: PipelineState,
    sample_document_metadata: DocumentMetadata,
) -> DocumentComplete:
    """Create a sample DocumentComplete composite."""
    return DocumentComplete(
        document=sample_document,
        pipeline=sample_pipeline_state,
        metadata=sample_document_metadata,
    )


@pytest.fixture
def sample_chunk_index(
    sample_tenant_id: str, sample_file_id: str, sample_chunk_id: str
) -> ChunkIndex:
    """Create a sample ChunkIndex entity."""
    return ChunkIndex(
        file_id=sample_file_id,
        chunk_id=sample_chunk_id,
        chunk_index=0,
        text_preview="This is the beginning of the document text...",
        start_char=0,
        end_char=500,
        page_number=1,
        # Blob storage references (SSOT for content location)
        chunk_blob_ref=f"{sample_tenant_id}/{sample_file_id}/chunks/{sample_chunk_id}.json",
    )





@pytest.fixture
def sample_chunks(sample_tenant_id: str, sample_file_id: str) -> list[ChunkIndex]:
    """Create a list of sample ChunkIndex entities."""
    chunks = []
    for i in range(5):
        chunks.append(
            ChunkIndex(
                file_id=sample_file_id,
                chunk_id=str(uuid4()),
                chunk_index=i,
                text_preview=f"Chunk {i} text content preview...",
                start_char=i * 500,
                end_char=(i + 1) * 500,
                page_number=i // 2 + 1,
            )
        )
    return chunks


# ============================================================================
# Mock Client Fixtures
# ============================================================================


@pytest.fixture
def mock_blob_client() -> MagicMock:
    """Create a mock BlobStorageClient."""
    client = MagicMock()
    client.upload_blob = AsyncMock(
        return_value={"etag": "test-etag", "last_modified": datetime.now(timezone.utc)}
    )
    client.download_blob = AsyncMock(return_value=b"test content")
    client.download_blob_to_text = AsyncMock(return_value="test content")
    client.delete_blob = AsyncMock(return_value=True)
    client.blob_exists = AsyncMock(return_value=True)
    client.list_blobs = AsyncMock(return_value=[])
    client.get_blob_properties = AsyncMock(
        return_value={"name": "test", "size": 100, "etag": "test-etag"}
    )
    client.create_container_if_not_exists = AsyncMock(return_value=True)
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_queue_client() -> MagicMock:
    """Create a mock QueueStorageClient."""
    client = MagicMock()
    client.send_message = AsyncMock(
        return_value={
            "message_id": "msg-123",
            "pop_receipt": "receipt-123",
            "operation_id": str(uuid4()),
            "correlation_id": str(uuid4()),
        }
    )
    client.send_raw_message = AsyncMock(
        return_value={"message_id": "msg-123", "pop_receipt": "receipt-123"}
    )
    client.receive_messages = AsyncMock(return_value=[])
    client.delete_message = AsyncMock(return_value=True)
    client.peek_messages = AsyncMock(return_value=[])
    client.clear_queue = AsyncMock()
    client.get_queue_properties = AsyncMock(
        return_value={"name": "test", "approximate_message_count": 0}
    )
    client.create_queue_if_not_exists = AsyncMock(return_value=True)
    client.close = AsyncMock()
    return client


# ============================================================================
# Integration Test Markers
# ============================================================================


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "requires_azurite: mark test as requiring Azurite to be running"
    )
    config.addinivalue_line(
        "markers",
        "requires_azure_di: mark test as requiring Azure Document Intelligence credentials",
    )
    config.addinivalue_line(
        "markers",
        "requires_azure_functions: mark test as requiring Azure Functions queue triggers to be running",
    )
    config.addinivalue_line(
        "markers",
        "requires_docling_models: mark test as requiring Docling's model artifacts on disk",
    )
    config.addinivalue_line(
        "markers",
        "end2end_http: mark test as end-to-end HTTP pipeline test requiring Azure credentials",
    )
    config.addinivalue_line(
        "markers",
        "end2end_queue: mark test as end-to-end queue pipeline test requiring Azure Functions",
    )


def _docker_is_available() -> bool:
    """Whether a Docker daemon is reachable for the testcontainers fixtures."""
    import subprocess

    try:
        return (
            subprocess.run(
                ["docker", "info"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


def _docling_models_are_available() -> bool:
    """Whether Docling and its model weights are both present.

    The weights are hundreds of megabytes and are fetched, not vendored, so a default
    `pytest` run must not need them: everything about the mapping is tested against a
    `DoclingDocument` built in memory, and only the conversion itself is gated here.
    """
    from importlib.util import find_spec

    if find_spec("docling") is None:
        return False

    from src.config.settings import get_settings as _get_settings

    configured = (_get_settings().docling.artifacts_path or "").strip()
    candidates = [Path(configured)] if configured else [Path.home() / ".cache/docling/models"]
    return any(path.is_dir() and any(path.iterdir()) for path in candidates)


def pytest_collection_modifyitems(config, items):
    """Skip tests based on environment configuration."""
    # SQL Server tests run against a testcontainer, so they need a Docker daemon. Without
    # one the session-scoped fixture raises during setup, which reads as a broken test
    # rather than an absent dependency.
    sqlserver_items = [item for item in items if "requires_sqlserver" in item.keywords]
    if sqlserver_items and (
        os.getenv("SKIP_SQLSERVER_TESTS") or not _docker_is_available()
    ):
        skip_sqlserver = pytest.mark.skip(
            reason="SQL Server tests need a running Docker daemon (or SKIP_SQLSERVER_TESTS is set)"
        )
        for item in sqlserver_items:
            item.add_marker(skip_sqlserver)

    if not _docling_models_are_available():
        skip_docling = pytest.mark.skip(
            reason="Docling model artifacts are absent; run `docling-tools models download`"
        )
        for item in items:
            if "requires_docling_models" in item.keywords:
                item.add_marker(skip_docling)

    # Skip Azurite tests if requested
    if os.getenv("SKIP_AZURITE_TESTS"):
        skip_azurite = pytest.mark.skip(reason="SKIP_AZURITE_TESTS is set")
        for item in items:
            if "requires_azurite" in item.keywords:
                item.add_marker(skip_azurite)

    # Skip Azure Document Intelligence tests if requested, not configured, or explicitly disabled via flag
    from src.config.settings import get_settings as _get_settings

    # DOCUMENT_INTELLIGENCE_RUN_TESTS is handled by the application's DocumentIntelligence settings.
    run_flag = _get_settings().document_intelligence.run_tests
    if run_flag and run_flag.lower() in ("0", "false", "no", "off"):
        should_run_di = False
    elif run_flag and run_flag.lower() in ("1", "true", "yes", "on"):
        should_run_di = True
    else:
        should_run_di = bool(
            os.getenv("DOCUMENT_INTELLIGENCE_ENDPOINT")
            or _get_settings().document_intelligence.is_configured
        )

    if os.getenv("SKIP_AZURE_DI_TESTS") or not should_run_di:
        skip_di = pytest.mark.skip(
            reason="Azure Document Intelligence not configured or tests disabled via DOCUMENT_INTELLIGENCE_RUN_TESTS"
        )
        for item in items:
            if "requires_azure_di" in item.keywords:
                item.add_marker(skip_di)

    # Skip Azure Functions queue trigger tests by default (requires func start)
    # Only run if explicitly enabled via RUN_AZURE_FUNCTIONS_TESTS env var
    if not os.getenv("RUN_AZURE_FUNCTIONS_TESTS"):
        skip_azure_functions = pytest.mark.skip(
            reason="Azure Functions queue triggers not running. Set RUN_AZURE_FUNCTIONS_TESTS=1 and run 'func start' to enable"
        )
        for item in items:
            if "requires_azure_functions" in item.keywords:
                item.add_marker(skip_azure_functions)

    # Skip end-to-end HTTP pipeline tests by default
    # Only run if explicitly enabled via RUN_END2END_HTTP_TESTS env var
    if not os.getenv("RUN_END2END_HTTP_TESTS"):
        skip_e2e_http = pytest.mark.skip(
            reason="End-to-end HTTP pipeline tests disabled. Set RUN_END2END_HTTP_TESTS=1 to enable"
        )
        for item in items:
            if "end2end_http" in item.keywords:
                item.add_marker(skip_e2e_http)

    # Skip end-to-end queue pipeline tests by default
    # Only run if explicitly enabled via RUN_END2END_QUEUE_TESTS env var
    if not os.getenv("RUN_END2END_QUEUE_TESTS"):
        skip_e2e_queue = pytest.mark.skip(
            reason="End-to-end queue pipeline tests disabled. Set RUN_END2END_QUEUE_TESTS=1 and run 'func start' to enable"
        )
        for item in items:
            if "end2end_queue" in item.keywords:
                item.add_marker(skip_e2e_queue)


# ============================================================================
# Document Analysis Fixtures
# ============================================================================


@pytest.fixture
def sample_markdown_output(sample_file_id: str) -> MarkdownOutput:
    """Create a sample MarkdownOutput entity."""
    return MarkdownOutput(
        file_id=sample_file_id,
        file_version=1,
        extracted_text="This is sample extracted text from the document.",
        pages=[
            PageContent(
                page_number=1,
                text="This is sample extracted text from the document.",
                word_count=8,
            )
        ],
        extraction_metadata=ExtractionMetadata(
            page_count=1,
            word_count=8,
            extraction_confidence=0.95,
            extraction_method="fake-document-intelligence",
            api_version="fake-1.0.0",
        ),
    )


@pytest.fixture
def mock_document_intelligence_adapter() -> MagicMock:
    """Create a mock DocumentIntelligencePort adapter."""
    adapter = MagicMock()
    adapter.analyze_document = AsyncMock()
    adapter.get_supported_formats = MagicMock(
        return_value=[
            "application/pdf",
            "image/png",
            "image/jpeg",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/plain",
        ]
    )
    adapter.is_format_supported = MagicMock(return_value=True)
    return adapter


@pytest.fixture
def fake_document_intelligence_adapter() -> FakeDocumentIntelligenceAdapter:
    """Create a FakeDocumentIntelligenceAdapter for testing."""
    return FakeDocumentIntelligenceAdapter(
        simulated_delay_seconds=0.01,  # Minimal delay for tests
        simulated_confidence=0.95,
    )


# ============================================================================
# Chunking Fixtures
# ============================================================================


@pytest.fixture
def chunking_settings():
    """Create ChunkingSettings for testing."""
    from src.config.settings import ChunkingSettings

    return ChunkingSettings(
        default_strategy="fixed_size",
        default_chunk_size=512,
        default_chunk_overlap=50,
        use_fake=True,
        run_tests="off",
    )


@pytest.fixture
def fake_chunker(chunking_settings):
    """Create a FakeChunker for testing."""
    from src.infrastructure.llamaindex.chunker_fake import FakeChunker

    return FakeChunker(simulated_delay_seconds=0.0)


@pytest.fixture
def mock_chunker():
    """Create a mock ChunkerPort."""
    from src.core.entities.chunk import Chunk, ChunkMetadata
    from src.core.value_objects.chunking_strategy import ChunkingStrategyName

    chunker = MagicMock()
    chunker.chunk_text = AsyncMock(
        return_value=[
            Chunk(
                file_id="test-file",
                chunk_id="test-file_chunk_0",
                chunk_index=0,
                text="First chunk content",
                start_char=0,
                end_char=19,
                metadata=ChunkMetadata(),
            ),
            Chunk(
                file_id="test-file",
                chunk_id="test-file_chunk_1",
                chunk_index=1,
                text="Second chunk content",
                start_char=19,
                end_char=39,
                metadata=ChunkMetadata(),
            ),
        ]
    )
    chunker.get_supported_strategies = MagicMock(
        return_value=[ChunkingStrategyName.FIXED_SIZE]
    )
    chunker.is_strategy_supported = MagicMock(return_value=True)
    return chunker


@pytest.fixture
def sample_text_for_chunking() -> str:
    """Create sample text content for chunking tests."""
    return """# Sample Document

This is a sample document for testing the chunking functionality.
It contains multiple paragraphs and sentences to ensure proper splitting.

## Section One

The quick brown fox jumps over the lazy dog. This sentence is here to add
more content. We want to have enough text to create multiple chunks.

## Section Two

Another section with different content. This helps test how the chunker
handles document structure. Multiple sentences add variety.

## Conclusion

Final section of the document with concluding remarks.
"""


@pytest.fixture
def sample_chunks_list(sample_file_id: str):
    """Create a list of sample Chunk entities."""
    from src.core.entities.chunk import Chunk, ChunkMetadata

    return [
        Chunk(
            file_id=sample_file_id,
            chunk_id=f"{sample_file_id}_chunk_{i}",
            chunk_index=i,
            text=f"This is chunk {i} content for testing purposes.",
            start_char=i * 100,
            end_char=(i + 1) * 100,
            page_number=i // 3 + 1,
            metadata=ChunkMetadata(
                chunking_strategy="fixed_size",
                chunk_size=100,
                overlap_chars=10,
            ),
        )
        for i in range(5)
    ]


# ============================================================================
# Embedding Fixtures
# ============================================================================


@pytest.fixture
def embedding_settings():
    """Create EmbeddingSettings for testing."""
    from src.config.settings import EmbeddingSettings

    return EmbeddingSettings(
        endpoint="https://fake-endpoint.openai.azure.com",
        api_key="fake-api-key",
        api_version="2024-02-01",
        default_model="text-embedding-3-small",
        deployment_name="text-embedding-3-small",
        max_batch_size=100,
        max_tokens_per_batch=8000,
        retry_delay_base=0.1,
        retry_delay_max=1.0,
        max_retries=3,
        use_fake=True,
        run_tests="off",
    )


@pytest.fixture
def fake_embeddings():
    """Create a FakeEmbeddings adapter for testing."""
    from src.infrastructure.azure.adapters.embedding_fake import FakeEmbeddings

    return FakeEmbeddings(simulated_delay_seconds=0.0)


@pytest.fixture
def mock_embedding_adapter():
    """Create a mock EmbeddingPort adapter."""
    from src.application.ports.embedding import EmbeddingResult

    adapter = MagicMock()
    adapter.generate_embeddings = AsyncMock(
        return_value=[
            EmbeddingResult(
                text="sample text",
                vector=[0.1] * 1536,
                token_count=10,
                model="text-embedding-3-small",
                dimension=1536,
            )
        ]
    )
    adapter.get_supported_models = MagicMock(
        return_value=["text-embedding-3-small", "text-embedding-3-large"]
    )
    adapter.get_model_dimension = MagicMock(
        side_effect=lambda m: 1536 if m == "text-embedding-3-small" else 3072
    )
    adapter.is_model_supported = MagicMock(
        side_effect=lambda m: m in ["text-embedding-3-small", "text-embedding-3-large"]
    )
    adapter.count_tokens = MagicMock(return_value=10)
    adapter.close = AsyncMock()
    return adapter


@pytest.fixture
def sample_embedding(sample_file_id: str, sample_chunk_id: str):
    """Create a sample Embedding entity."""
    from src.core.entities.embedding import Embedding, EmbeddingMetadata

    return Embedding(
        file_id=sample_file_id,
        chunk_id=sample_chunk_id,
        embedding_model="text-embedding-3-small",
        embedding_dimension=1536,
        vector=[0.1] * 1536,
        chunk_text="Sample chunk text for embedding.",
        metadata=EmbeddingMetadata(
            model_version="text-embedding-3-small",
            token_count=10,
            chunking_strategy="fixed_size",
            chunk_size=512,
            overlap_chars=50,
        ),
    )


@pytest.fixture
def vectorize_request(sample_file_id: str, sample_tenant_id: str):
    """Create a sample VectorizeChunksRequest."""
    from src.application.dto.embedding import VectorizeChunksRequest

    return VectorizeChunksRequest(
        file_id=sample_file_id,
        tenant_id=sample_tenant_id,
        file_version=1,
        embedding_model="text-embedding-3-small",
        batch_size=50,
    )


# ============================================================================
# Container and Dependency Injection Fixtures
# ============================================================================


@pytest.fixture
def container() -> Container:
    """Create a fresh Container instance for testing."""
    return Container()


@pytest.fixture
def mock_process_document_use_case() -> AsyncMock:
    """Create a mock ProcessDocumentUseCase for testing."""
    mock = AsyncMock()
    mock.execute = AsyncMock()
    return mock


@pytest.fixture
def mock_vector_database() -> AsyncMock:
    """Create a mock vector database adapter for testing."""
    mock = AsyncMock()
    mock.search = AsyncMock(return_value=[])
    mock.ingest_documents = AsyncMock(return_value={"successful": 0, "failed": 0})
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def container_with_mocks(container: Container, mock_process_document_use_case):
    """Create a container with mocked dependencies for testing."""
    # Override key providers with mocks
    container.process_document_use_case.override(mock_process_document_use_case)
    yield container
    # Cleanup is automatic when context exits
