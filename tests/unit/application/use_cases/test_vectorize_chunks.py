"""Unit tests for VectorizeChunksUseCase."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.dto.document_analysis import ProcessingStatus
from src.application.dto.embedding import VectorizeChunksRequest
from src.application.ports.embedding import EmbeddingResult
from src.application.use_cases.vectorize_chunks import VectorizeChunksUseCase
from src.core.entities.chunk import Chunk, ChunkMetadata
from src.core.entities.composites import DocumentWithPipeline
from src.core.entities.document import Document
from src.core.entities.pipeline_state import OverallStatus, PipelineState, ProcessingStage


@pytest.fixture
def mock_blob_client() -> MagicMock:
    client = MagicMock()
    client.upload_blob = AsyncMock(return_value={})
    client.download_blob = AsyncMock()
    return client


@pytest.fixture
def mock_embedding_port() -> MagicMock:
    port = MagicMock()
    port.get_model_dimension = MagicMock(return_value=1536)
    port.generate_embeddings = AsyncMock(
        return_value=[
            EmbeddingResult(
                text="chunk text",
                vector=[0.1] * 1536,
                token_count=12,
                model="text-embedding-3-small",
                dimension=1536,
            )
        ]
    )
    return port


@pytest.fixture
def mock_chunk_index_repo() -> MagicMock:
    repo = MagicMock()
    repo.query_pending_embeddings = AsyncMock()
    repo.count_by_file = AsyncMock(return_value=1)
    repo.batch_get_metadata = AsyncMock(return_value={})
    repo.mark_embedded = AsyncMock()
    repo.mark_failed = AsyncMock()
    return repo


@pytest.fixture
def mock_pipeline_store() -> MagicMock:
    store = MagicMock()
    store.get_by_id = AsyncMock(
        return_value=DocumentWithPipeline(
            document=Document(
                tenant_id="tenant-1",
                file_id="file-1",
                blob_name="doc.pdf",
                content_type="application/pdf",
                size_bytes=1000,
                content_hash="abc",
                file_version=1,
            ),
            pipeline=PipelineState(
                file_id="file-1",
                current_stage=ProcessingStage.VECTORIZE,
                overall_status=OverallStatus.PROCESSING,
                chunk_count=1,
                embedded_chunk_count=0,
                chunking_strategy="fixed_size",
                embedding_model="text-embedding-3-small",
                vector_db_targets='["azure-ai-search"]',
            ),
        )
    )
    store.mark_processing = AsyncMock()
    store.update_embedded_count = AsyncMock()
    store.mark_failed = AsyncMock()
    return store


def _make_chunk_index(chunk_id: str, file_id: str = "file-1") -> MagicMock:
    ci = MagicMock()
    ci.chunk_id = chunk_id
    ci.chunk_blob_ref = f"tenant-1/{file_id}/chunks/{chunk_id}.json"
    return ci


def _make_chunk(chunk_id: str, text: str = "chunk text", page_number: int | None = None) -> Chunk:
    return Chunk(
        file_id="file-1",
        chunk_id=chunk_id,
        chunk_index=0,
        text=text,
        start_char=0,
        end_char=len(text),
        page_number=page_number,
        metadata=ChunkMetadata(
            chunking_strategy="old_strategy",
            chunk_size=999,
            overlap_chars=999,
            has_table=False,
            section_path=["Old"],
        ),
    )


@pytest.fixture
def use_case(
    mock_blob_client,
    mock_embedding_port,
    mock_chunk_index_repo,
    mock_pipeline_store,
) -> VectorizeChunksUseCase:
    return VectorizeChunksUseCase(
        blob_client=mock_blob_client,
        embedding_port=mock_embedding_port,
        chunk_index_repository=mock_chunk_index_repo,
        pipeline_store=mock_pipeline_store,
    )


@pytest.fixture
def request_obj() -> VectorizeChunksRequest:
    return VectorizeChunksRequest(
        file_id="file-1",
        tenant_id="tenant-1",
        file_version=1,
        source_container="chunks",
        output_container="embeddings",
        embedding_model="text-embedding-3-small",
        batch_size=10,
    )


class TestProcessBatchMetadataSourced:
    """_process_batch must source all EmbeddingMetadata fields from metadata_map."""

    async def test_metadata_fields_come_from_sql(self, use_case):
        chunk = _make_chunk("chunk-1")
        sql_meta = {
            "token_count": 42,
            "chunking_strategy": "semantic",
            "chunk_size": 512,
            "overlap_chars": 50,
            "section_path": ["Introduction", "Background"],
            "has_table": True,
            "table_id": "table_0",
        }

        embeddings = await use_case._process_batch(
            chunks=[chunk],
            model="text-embedding-3-small",
            request=MagicMock(file_id="file-1"),
            metadata_map={"chunk-1": sql_meta},
        )

        assert len(embeddings) == 1
        meta = embeddings[0].metadata
        assert meta.token_count == 42
        assert meta.chunking_strategy == "semantic"
        assert meta.chunk_size == 512
        assert meta.overlap_chars == 50
        assert meta.section_path == ["Introduction", "Background"]
        assert meta.has_table is True
        assert meta.table_id == "table_0"

    async def test_chunking_strategy_is_per_chunk_not_doc_level(self, use_case):
        chunk = _make_chunk("chunk-1")
        sql_meta = {"chunking_strategy": "recursive", "chunk_size": 256}

        embeddings = await use_case._process_batch(
            chunks=[chunk],
            model="text-embedding-3-small",
            request=MagicMock(file_id="file-1"),
            metadata_map={"chunk-1": sql_meta},
        )

        assert embeddings[0].metadata.chunking_strategy == "recursive"

    async def test_chunk_size_from_sql_not_zero(self, use_case):
        chunk = _make_chunk("chunk-1")

        embeddings = await use_case._process_batch(
            chunks=[chunk],
            model="text-embedding-3-small",
            request=MagicMock(file_id="file-1"),
            metadata_map={"chunk-1": {"chunk_size": 1024, "chunking_strategy": "fixed_size"}},
        )

        assert embeddings[0].metadata.chunk_size == 1024

    async def test_fallback_defaults_when_chunk_not_in_map(self, use_case):
        chunk = _make_chunk("chunk-missing")

        embeddings = await use_case._process_batch(
            chunks=[chunk],
            model="text-embedding-3-small",
            request=MagicMock(file_id="file-1"),
            metadata_map={},
        )

        meta = embeddings[0].metadata
        assert meta.chunking_strategy == ""
        assert meta.chunk_size == 0
        assert meta.overlap_chars == 0
        assert meta.has_table is False
        assert meta.table_id is None
        assert meta.section_path is None

    async def test_blob_metadata_fields_ignored(self, use_case):
        """Fields from chunk.metadata (blob) must NOT bleed into EmbeddingMetadata."""
        chunk = _make_chunk("chunk-1")
        # chunk.metadata has old_strategy/999/999/Old — these must be ignored
        sql_meta = {"chunking_strategy": "fixed_size", "chunk_size": 512, "overlap_chars": 25}

        embeddings = await use_case._process_batch(
            chunks=[chunk],
            model="text-embedding-3-small",
            request=MagicMock(file_id="file-1"),
            metadata_map={"chunk-1": sql_meta},
        )

        meta = embeddings[0].metadata
        assert meta.chunking_strategy == "fixed_size"
        assert meta.chunk_size == 512
        assert meta.overlap_chars == 25

    async def test_page_number_propagated_from_chunk(self, use_case):
        """page_number from Chunk must be propagated to EmbeddingMetadata."""
        chunk = _make_chunk("chunk-1", page_number=5)

        embeddings = await use_case._process_batch(
            chunks=[chunk],
            model="text-embedding-3-small",
            request=MagicMock(file_id="file-1"),
            metadata_map={"chunk-1": {}},
        )

        assert embeddings[0].metadata.page_number == 5

    async def test_page_number_none_when_chunk_has_no_page(self, use_case):
        """page_number must be None in EmbeddingMetadata when Chunk has no page_number."""
        chunk = _make_chunk("chunk-1", page_number=None)

        embeddings = await use_case._process_batch(
            chunks=[chunk],
            model="text-embedding-3-small",
            request=MagicMock(file_id="file-1"),
            metadata_map={"chunk-1": {}},
        )

        assert embeddings[0].metadata.page_number is None

    async def test_page_number_in_model_dump_reaches_ingestion(self, use_case):
        """page_number must survive model_dump so the ingest trigger can read it."""
        chunk = _make_chunk("chunk-1", page_number=3)

        embeddings = await use_case._process_batch(
            chunks=[chunk],
            model="text-embedding-3-small",
            request=MagicMock(file_id="file-1"),
            metadata_map={"chunk-1": {}},
        )

        dumped = embeddings[0].metadata.model_dump(mode="json")
        assert dumped["page_number"] == 3


class TestExecuteBatchGetMetadataCalled:
    """execute() must call batch_get_metadata with the loaded chunk IDs."""

    async def test_batch_get_metadata_called_with_chunk_ids(
        self, use_case, mock_blob_client, mock_chunk_index_repo, request_obj
    ):
        chunk = _make_chunk("chunk-abc")
        chunk_index = _make_chunk_index("chunk-abc")
        mock_chunk_index_repo.query_pending_embeddings = AsyncMock(return_value=[chunk_index])
        mock_chunk_index_repo.batch_get_metadata = AsyncMock(return_value={})
        mock_blob_client.download_blob = AsyncMock(
            return_value=json.dumps(chunk.model_dump(mode="json"))
        )

        await use_case.execute(request_obj)

        mock_chunk_index_repo.batch_get_metadata.assert_awaited_once_with(["chunk-abc"])
