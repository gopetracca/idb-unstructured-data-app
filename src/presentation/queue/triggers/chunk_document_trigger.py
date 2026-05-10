"""Queue trigger for document chunking."""

import logging

import azure.functions as func
from dependency_injector.wiring import Provide, inject

from src.application.dto.queue_message import QueueMessageEnvelope
from src.application.ports.pipeline_store import PipelineStorePort
from src.application.use_cases.chunk_document_and_enqueue_vectorization import (
    ChunkDocumentAndEnqueueVectorizationUseCase,
)
from src.container import Container
from src.utils.dd_span import queue_span

logger = logging.getLogger(__name__)

bp = func.Blueprint()


@bp.queue_trigger(
    arg_name="msg",
    queue_name="text-to-chunks",
    connection="",
)
async def chunk_document_trigger(
    msg: func.QueueMessage,
) -> None:
    raw_body = msg.get_body().decode("utf-8")
    envelope = QueueMessageEnvelope.from_queue_message(raw_body)
    async with queue_span("text-to-chunks", envelope):
        await _handle_chunk_document_trigger(msg, envelope)


@inject
async def _handle_chunk_document_trigger(
    msg: func.QueueMessage,
    envelope: QueueMessageEnvelope,
    chunk_use_case: ChunkDocumentAndEnqueueVectorizationUseCase = Provide[
        Container.chunk_document_and_enqueue_vectorization_use_case
    ],
    pipeline_store: PipelineStorePort = Provide[Container.document_repository],
) -> None:
    """
    Handle text-to-chunks queue messages.

    Calls ChunkDocumentUseCase to chunk extracted text.
    """
    logger.info("[chunk_document_trigger] START - received message")

    try:
        raw_body = msg.get_body().decode("utf-8")
        logger.info(f"[chunk_document_trigger] Raw message: {raw_body[:500]}")

        from src.application.dto.chunking import ChunkDocumentRequest
        from src.config.settings import get_settings
        from src.core.value_objects.chunking_strategy import ChunkingStrategy
        from src.presentation.queue.common.error_handler import with_error_handling

        settings = get_settings()

        logger.info(
            f"[chunk_document_trigger] Processing document: file_id={envelope.file_id}, "
            f"tenant_id={envelope.tenant_id}, correlation_id={envelope.correlation_id}"
        )

        payload = envelope.payload or {}
        source_container = payload.get("source_container") or settings.azure_storage.container_text
        output_container = payload.get("output_container") or settings.azure_storage.container_chunks

        chunking_strategy_payload = payload.get("chunking_strategy")
        if isinstance(chunking_strategy_payload, dict):
            chunking_strategy = ChunkingStrategy.model_validate(chunking_strategy_payload)
        else:
            chunking_strategy = ChunkingStrategy.fixed_size()

        async def execute() -> None:
            request = ChunkDocumentRequest(
                file_id=envelope.file_id,
                tenant_id=envelope.tenant_id,
                source_container=source_container,
                output_container=output_container,
                chunking_strategy=chunking_strategy,
                correlation_id=envelope.correlation_id,
            )

            logger.info(
                f"[chunk_document_trigger] Executing use case for file_id={envelope.file_id}"
            )

            result = await chunk_use_case.execute(request)

            logger.info(
                f"[chunk_document_trigger] Document chunked: file_id={envelope.file_id}, "
                f"status={result.status}, chunk_count={result.chunk_count}"
            )

        await with_error_handling(
            envelope=envelope,
            pipeline_store=pipeline_store,
            operation=execute,
            operation_name="chunk_document",
        )

        logger.info(
            f"[chunk_document_trigger] COMPLETED successfully for file_id={envelope.file_id}"
        )

    except Exception as e:
        error_msg = f"[chunk_document_trigger] FAILED with error: {type(e).__name__}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise
