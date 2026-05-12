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
    logger.debug("chunk_document_trigger received message")

    try:
        raw_body = msg.get_body().decode("utf-8")
        logger.debug("chunk_document_trigger raw message: %s", raw_body[:500])

        from src.application.dto.chunking import ChunkDocumentRequest
        from src.config.settings import get_settings
        from src.core.value_objects.chunking_strategy import ChunkingStrategy
        from src.presentation.queue.common.error_handler import with_error_handling

        settings = get_settings()

        logger.debug(
            "chunk_document_trigger processing: file_id=%s, tenant_id=%s, correlation_id=%s",
            envelope.file_id,
            envelope.tenant_id,
            envelope.correlation_id,
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

            result = await chunk_use_case.execute(request)

            logger.debug(
                "chunk_document_trigger result: file_id=%s, status=%s, chunk_count=%s",
                envelope.file_id,
                result.status,
                result.chunk_count,
            )
            logger.info(
                "chunk_document completed: file_id=%s, chunks=%d, status=%s",
                envelope.file_id,
                result.chunk_count,
                result.status,
            )

        await with_error_handling(
            envelope=envelope,
            pipeline_store=pipeline_store,
            operation=execute,
            operation_name="chunk_document",
        )

    except Exception:
        raise
