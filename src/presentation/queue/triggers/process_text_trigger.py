"""Queue trigger for the document text extraction stage."""

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

    Extracts text via the configured extraction adapter and enqueues chunking.
    """
    logger.debug("process_text_trigger received message")

    try:
        raw_body = msg.get_body().decode("utf-8")
        logger.debug("process_text_trigger raw message: %s", raw_body[:500])

        from src.application.dto.document_analysis import DocumentAnalysisRequest
        from src.config.settings import get_settings
        from src.presentation.queue.common.error_handler import with_error_handling

        settings = get_settings()

        logger.debug(
            "process_text_trigger processing: file_id=%s, tenant_id=%s, correlation_id=%s",
            envelope.file_id,
            envelope.tenant_id,
            envelope.correlation_id,
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

            result = await process_use_case.execute(
                request, chunking_strategy=chunking_strategy
            )

            logger.debug(
                "process_text_trigger result: file_id=%s, status=%s, processing_time_ms=%s",
                envelope.file_id,
                result.status,
                result.processing_time_ms,
            )
            logger.info(
                "process_text completed: file_id=%s, status=%s, ms=%s",
                envelope.file_id,
                result.status,
                result.processing_time_ms,
            )

        await with_error_handling(
            envelope=envelope,
            pipeline_store=pipeline_store,
            operation=execute,
            operation_name="process_text",
        )

    except Exception:
        raise
