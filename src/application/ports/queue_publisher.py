"""Port for publishing messages to queues."""

from abc import ABC, abstractmethod
from typing import Any


class QueuePublisherPort(ABC):
    """Abstract interface for queue message publishing."""

    @abstractmethod
    async def publish(
        self,
        queue_name: str,
        tenant_id: str,
        file_id: str,
        file_version: int = 1,
        payload: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Publish a message to the specified queue.

        Args:
            queue_name: Name of the target queue
            tenant_id: Tenant identifier
            file_id: File identifier
            file_version: File version number
            payload: Additional message data
            correlation_id: Optional correlation ID for tracing

        Returns:
            Message metadata including message_id and operation_id
        """
        pass
