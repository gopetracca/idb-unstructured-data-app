"""Azure Queue Storage adapter for queue publishing."""

from typing import Any

from src.application.ports.queue_publisher import QueuePublisherPort
from src.infrastructure.azure.clients.queue_client import QueueStorageClient


class AzureQueuePublisher(QueuePublisherPort):
    """Azure implementation of queue publisher port."""

    def __init__(self, queue_client: QueueStorageClient) -> None:
        """
        Initialize the Azure queue publisher.

        Args:
            queue_client: QueueStorageClient instance for Azure Queue Storage operations
        """
        self._queue_client = queue_client

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
        Publish a message to the specified Azure queue.

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
        return await self._queue_client.send_message(
            queue=queue_name,
            tenant_id=tenant_id,
            file_id=file_id,
            file_version=file_version,
            payload=payload,
            correlation_id=correlation_id,
        )
