"""Queue trigger for vector database ingestion."""

import json
import logging

import azure.functions as func
from dependency_injector.wiring import Provide, inject

from src.application.dto.queue_message import QueueMessageEnvelope
from src.application.ports.blob_client import BlobClientPort
from src.application.ports.pipeline_store import PipelineStorePort
from src.application.use_cases.ingest_documents import IngestDocumentsUseCase
from src.container import Container
from src.utils.dd_span import queue_span

logger = logging.getLogger(__name__)

bp = func.Blueprint()


@bp.queue_trigger(
    arg_name="msg",
    queue_name="ingest-to-db",
    connection="",
)
async def ingest_into_db_trigger(
    msg: func.QueueMessage,
) -> None:
    raw_body = msg.get_body().decode("utf-8")
    envelope = QueueMessageEnvelope.from_queue_message(raw_body)
    async with queue_span("ingest-to-db", envelope):
        await _handle_ingest_into_db_trigger(msg, envelope)


@inject
async def _handle_ingest_into_db_trigger(
    msg: func.QueueMessage,
    envelope: QueueMessageEnvelope,
    ingest_use_case: IngestDocumentsUseCase = Provide[Container.ingest_documents_use_case],
    pipeline_store: PipelineStorePort = Provide[Container.document_repository],
    blob_client: BlobClientPort = Provide[Container.blob_store_adapter],
) -> None:
    """
    Handle ingest-to-db queue messages.

    Loads embeddings from blob storage and ingests them into the vector database.
    """
    logger.info("[ingest_into_db_trigger] START - received message")

    try:
        raw_body = msg.get_body().decode("utf-8")
        logger.info(f"[ingest_into_db_trigger] Raw message: {raw_body[:500]}")

        from src.application.dto.ingestion_dto import IngestDocumentsInput, IngestionDocument
        from src.config.settings import get_settings
        from src.presentation.queue.common.error_handler import with_error_handling

        settings = get_settings()

        logger.info(
            f"[ingest_into_db_trigger] Processing document: file_id={envelope.file_id}, "
            f"tenant_id={envelope.tenant_id}, correlation_id={envelope.correlation_id}"
        )

        payload = envelope.payload or {}
        collection_name = payload.get("collection_name")
        if not collection_name:
            raise ValueError("collection_name is required in payload")

        source_container = (
            payload.get("source_container")
            or settings.azure_storage.container_embeddings
        )

        async def execute() -> None:
            logger.info(
                f"[ingest_into_db_trigger] Loading embeddings from container={source_container}, "
                f"file_id={envelope.file_id}"
            )

            embeddings = await _load_embeddings_for_file(
                blob_client=blob_client,
                container=source_container,
                tenant_id=envelope.tenant_id,
                file_id=envelope.file_id,
            )

            if not embeddings:
                logger.warning(
                    f"[ingest_into_db_trigger] No embeddings found for file_id={envelope.file_id}"
                )
                return

            logger.info(
                f"[ingest_into_db_trigger] Loaded {len(embeddings)} embeddings for file_id={envelope.file_id}"
            )

            documents = [
                IngestionDocument(
                    id=f"{emb.file_id}_{emb.chunk_id}",
                    chunk_id=emb.chunk_id,
                    file_id=emb.file_id,
                    text=emb.chunk_text,
                    vector=emb.vector,
                    metadata=_filter_metadata(emb.metadata.model_dump(mode="json") if emb.metadata else {}),
                )
                for emb in embeddings
            ]

            input_dto = IngestDocumentsInput(
                tenant_id=envelope.tenant_id,
                collection_name=collection_name,
                documents=documents,
                correlation_id=envelope.correlation_id,
            )

            logger.info(
                f"[ingest_into_db_trigger] Executing use case for file_id={envelope.file_id}, "
                f"collection={collection_name}, document_count={len(documents)}"
            )

            result = await ingest_use_case.execute(input_dto)

            logger.info(
                f"[ingest_into_db_trigger] Ingestion completed: file_id={envelope.file_id}, "
                f"collection={collection_name}, successful={result.successful}, "
                f"failed={result.failed}"
            )

            if result.failed == 0:
                await pipeline_store.mark_completed(
                    envelope.tenant_id, envelope.file_id
                )
            else:
                await pipeline_store.mark_failed(
                    envelope.tenant_id,
                    envelope.file_id,
                    f"Ingestion partially failed: {result.failed}/{result.total_documents}",
                )

        await with_error_handling(
            envelope=envelope,
            pipeline_store=pipeline_store,
            operation=execute,
            operation_name="ingest_into_db",
        )

        logger.info(
            f"[ingest_into_db_trigger] COMPLETED successfully for file_id={envelope.file_id}"
        )

    except Exception as e:
        error_msg = (
            f"[ingest_into_db_trigger] FAILED with error: {type(e).__name__}: {str(e)}"
        )
        logger.error(error_msg, exc_info=True)
        raise
    finally:
        # Shared clients are closed on host shutdown in function_app.py.
        pass


async def _load_embeddings_for_file(
    blob_client: BlobClientPort,
    container: str,
    tenant_id: str,
    file_id: str,
) -> list:
    """
    Load all embeddings for a file from blob storage.

    Args:
        blob_client: BlobStorageClient instance
        container: Container name where embeddings are stored
        tenant_id: Tenant identifier
        file_id: File identifier

    Returns:
        List of Embedding entities
    """
    from src.core.entities.embedding import Embedding

    prefix = f"{tenant_id}/{file_id}/embeddings/"
    blobs = await blob_client.list_blobs(container, prefix=prefix)

    embeddings = []
    for blob in blobs:
        if not blob["name"].endswith(".json"):
            continue

        try:
            content = await blob_client.download_blob(container, blob["name"])
            data = json.loads(content)
            embedding = Embedding.model_validate(data)
            embeddings.append(embedding)
        except Exception as e:
            logger.warning(
                f"[ingest_into_db_trigger] Failed to load embedding {blob['name']}: {e}"
            )

    return embeddings


def _filter_metadata(metadata: dict) -> dict:
    """
    Filter metadata to only include fields supported by the vector database schema.

    Removes fields like 'created_at' that aren't defined in the Azure AI Search index.

    Args:
        metadata: Raw metadata dictionary from embedding

    Returns:
        Filtered metadata dictionary
    """
    excluded_fields = {"created_at"}
    filtered = {k: v for k, v in metadata.items() if k not in excluded_fields}
    return filtered
