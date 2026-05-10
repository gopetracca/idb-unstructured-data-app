"""Queue trigger for document text extraction (Document Intelligence)."""

import logging

import azure.functions as func
from dependency_injector.wiring import Provide, inject

from src.application.dto.queue_message import QueueMessageEnvelope
from src.application.ports.pipeline_store import PipelineStorePort
from src.application.use_cases.process_text_and_enqueue_chunking import (
    ProcessTextAndEnqueueChunkingUseCase,
)
from src.container import Container
from src.utils.dd_span import queue_span

logger = logging.getLogger(__name__)

bp = func.Blueprint()


@bp.queue_trigger(
    arg_name="msg",
    queue_name="raw-to-text",
    connection="",
)
async def process_text_trigger(
    msg: func.QueueMessage,
) -> None:
    raw_body = msg.get_body().decode("utf-8")
    envelope = QueueMessageEnvelope.from_queue_message(raw_body)
    async with queue_span("raw-to-text", envelope):
        await _handle_process_text_trigger(msg, envelope)


@inject
async def _handle_process_text_trigger(
    msg: func.QueueMessage,
    envelope: QueueMessageEnvelope,
    process_use_case: ProcessTextAndEnqueueChunkingUseCase = Provide[
        Container.process_text_and_enqueue_chunking_use_case
    ],
    pipeline_store: PipelineStorePort = Provide[Container.document_repository],
) -> None:
    """
    Handle raw-to-text queue messages.

    Extracts text via Document Intelligence and enqueues chunking.
    """
    logger.info("[process_text_trigger] START - received message")

    try:
        raw_body = msg.get_body().decode("utf-8")
        logger.info(f"[process_text_trigger] Raw message: {raw_body[:500]}")

        from src.application.dto.document_analysis import DocumentAnalysisRequest
        from src.config.settings import get_settings
        from src.presentation.queue.common.error_handler import with_error_handling

        settings = get_settings()

        logger.info(
            f"[process_text_trigger] Processing document: file_id={envelope.file_id}, "
            f"tenant_id={envelope.tenant_id}, correlation_id={envelope.correlation_id}"
        )

        payload = envelope.payload or {}
        chunking_strategy = payload.get("chunking_strategy")

        async def execute() -> None:
            request = DocumentAnalysisRequest(
                file_id=envelope.file_id,
                tenant_id=envelope.tenant_id,
                source_container=settings.azure_storage.container_raw,
                output_container=settings.azure_storage.container_text,
                correlation_id=envelope.correlation_id,
            )

            logger.info(f"[process_text_trigger] Executing use case for file_id={envelope.file_id}")

            result = await process_use_case.execute(
                request, chunking_strategy=chunking_strategy
            )

            logger.info(
                f"[process_text_trigger] Document processed: file_id={envelope.file_id}, "
                f"status={result.status}, processing_time_ms={result.processing_time_ms}"
            )

        await with_error_handling(
            envelope=envelope,
            pipeline_store=pipeline_store,
            operation=execute,
            operation_name="process_text",
        )

        logger.info(f"[process_text_trigger] COMPLETED successfully for file_id={envelope.file_id}")

    except Exception as e:
        error_msg = f"[process_text_trigger] FAILED with error: {type(e).__name__}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise
