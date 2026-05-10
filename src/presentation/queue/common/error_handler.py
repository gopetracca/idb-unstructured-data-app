"""Standardized error handling for queue triggers."""

import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from src.application.dto.queue_message import QueueMessageEnvelope
from src.application.ports.pipeline_store import PipelineStorePort

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def with_error_handling(
    envelope: QueueMessageEnvelope,
    pipeline_store: PipelineStorePort,
    operation: Callable[[], Awaitable[T]],
    operation_name: str,
) -> T:
    """
    Execute operation with standardized error handling.

    On failure:
    1. Updates pipeline state status to FAILED
    2. Logs the error with correlation ID
    3. Re-raises the exception for Azure Functions retry handling
    """
    try:
        return await operation()
    except Exception as e:
        logger.error(
            f"{operation_name} failed: file_id={envelope.file_id}, "
            f"tenant_id={envelope.tenant_id}, "
            f"correlation_id={envelope.correlation_id}, "
            f"error={str(e)}",
            exc_info=True,
        )

        # Update pipeline state to failed status
        try:
            await pipeline_store.mark_failed(
                tenant_id=envelope.tenant_id,
                file_id=envelope.file_id,
                error_message=str(e),
            )
        except Exception as status_error:
            logger.error(
                f"Failed to update pipeline state: file_id={envelope.file_id}, "
                f"error={status_error}"
            )

        # Re-raise for Azure Functions retry logic
        raise
