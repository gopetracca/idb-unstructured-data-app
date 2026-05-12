"""Queue message parsing utilities."""

import logging

from src.application.dto.queue_message import QueueMessageEnvelope

logger = logging.getLogger(__name__)


def parse_queue_message(raw_content: str) -> QueueMessageEnvelope:
    """
    Parse raw queue message content into structured envelope.

    Args:
        raw_content: Raw JSON string from queue message

    Returns:
        Parsed QueueMessageEnvelope

    Raises:
        ValueError: If message cannot be parsed
    """
    try:
        envelope = QueueMessageEnvelope.from_queue_message(raw_content)
        logger.debug(
            f"Parsed queue message: file_id={envelope.file_id}, "
            f"tenant_id={envelope.tenant_id}, "
            f"correlation_id={envelope.correlation_id}"
        )
        return envelope
    except ValueError:
        raise
    except Exception as e:
        logger.error("Unexpected error parsing queue message: %s", e, exc_info=True)
        raise ValueError(f"Failed to parse queue message: {e}") from e
