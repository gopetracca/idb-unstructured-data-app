"""Queue trigger for chunk vectorization."""

import logging

import azure.functions as func
from dependency_injector.wiring import Provide, inject

from src.application.dto.queue_message import QueueMessageEnvelope
from src.application.ports.pipeline_store import PipelineStorePort
from src.application.use_cases.vectorize_chunks_and_enqueue_ingestion import (
    VectorizeChunksAndEnqueueIngestionUseCase,
)
from src.container import Container
from src.utils.dd_span import queue_span

logger = logging.getLogger(__name__)

bp = func.Blueprint()


@bp.queue_trigger(
    arg_name="msg",
    queue_name="chunk-to-vector",
    connection="",
)
async def vectorize_chunks_trigger(
    msg: func.QueueMessage,
) -> None:
    raw_body = msg.get_body().decode("utf-8")
    envelope = QueueMessageEnvelope.from_queue_message(raw_body)
    async with queue_span("chunk-to-vector", envelope):
        await _handle_vectorize_chunks_trigger(msg, envelope)


@inject
async def _handle_vectorize_chunks_trigger(
    msg: func.QueueMessage,
    envelope: QueueMessageEnvelope,
    vectorize_use_case: VectorizeChunksAndEnqueueIngestionUseCase = Provide[
        Container.vectorize_chunks_and_enqueue_ingestion_use_case
    ],
    pipeline_store: PipelineStorePort = Provide[Container.document_repository],
) -> None:
    """
    Handle chunk-to-vector queue messages.

    Calls VectorizeChunksUseCase to generate embeddings.
    """
    logger.info("[vectorize_chunks_trigger] START - received message")

    try:
        raw_body = msg.get_body().decode("utf-8")
        logger.info(f"[vectorize_chunks_trigger] Raw message: {raw_body[:500]}")

        from src.application.dto.embedding import VectorizeChunksRequest
        from src.config.settings import get_settings
        from src.presentation.queue.common.error_handler import with_error_handling

        settings = get_settings()

        logger.info(
            f"[vectorize_chunks_trigger] Processing document: file_id={envelope.file_id}, "
            f"tenant_id={envelope.tenant_id}, correlation_id={envelope.correlation_id}"
        )

        payload = envelope.payload or {}
        source_container = payload.get("source_container") or settings.azure_storage.container_chunks
        output_container = payload.get("output_container") or settings.azure_storage.container_embeddings
        embedding_model = payload.get("embedding_model") or settings.embedding.default_model

        batch_size_raw = payload.get("batch_size")
        if isinstance(batch_size_raw, int):
            batch_size = batch_size_raw
        elif isinstance(batch_size_raw, str) and batch_size_raw.isdigit():
            batch_size = int(batch_size_raw)
        else:
            batch_size = min(settings.embedding.max_batch_size, 100)

        if batch_size < 1:
            batch_size = 1
        if batch_size > 100:
            batch_size = 100

        async def execute() -> None:
            request = VectorizeChunksRequest(
                file_id=envelope.file_id,
                tenant_id=envelope.tenant_id,
                file_version=envelope.file_version,
                source_container=source_container,
                output_container=output_container,
                embedding_model=embedding_model,
                batch_size=batch_size,
                correlation_id=envelope.correlation_id,
            )

            logger.info(
                f"[vectorize_chunks_trigger] Executing use case for file_id={envelope.file_id}"
            )

            result = await vectorize_use_case.execute(request)

            logger.info(
                f"[vectorize_chunks_trigger] Vectorization completed: file_id={envelope.file_id}, "
                f"status={result.status}, embedded={result.embedded_chunks}, "
                f"failed={result.failed_chunks}"
            )

        await with_error_handling(
            envelope=envelope,
            pipeline_store=pipeline_store,
            operation=execute,
            operation_name="vectorize_chunks",
        )

        logger.info(
            f"[vectorize_chunks_trigger] COMPLETED successfully for file_id={envelope.file_id}"
        )

    except Exception as e:
        error_msg = f"[vectorize_chunks_trigger] FAILED with error: {type(e).__name__}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise
