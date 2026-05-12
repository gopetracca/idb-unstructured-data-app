"""Azure Queue Storage client for message operations."""

import json
import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from azure.storage.queue import (
    QueueServiceClient,
    TextBase64DecodePolicy,
    TextBase64EncodePolicy,
)
from azure.storage.queue.aio import QueueServiceClient as AsyncQueueServiceClient

from src.config.settings import AzureStorageSettings, get_settings
from src.infrastructure.azure.clients.credentials import get_azure_credential


class QueueMessage:
    """Wrapper for queue message with parsed content."""

    def __init__(
        self,
        message_id: str,
        pop_receipt: str,
        content: dict[str, Any],
        dequeue_count: int,
        inserted_on: datetime | None = None,
        expires_on: datetime | None = None,
    ) -> None:
        self.message_id = message_id
        self.pop_receipt = pop_receipt
        self.content = content
        self.dequeue_count = dequeue_count
        self.inserted_on = inserted_on
        self.expires_on = expires_on

    @property
    def tenant_id(self) -> str:
        """Get tenant ID from message content."""
        return self.content.get("tenantId", "")

    @property
    def file_id(self) -> str:
        """Get file ID from message content."""
        return self.content.get("fileId", "")

    @property
    def operation_id(self) -> str:
        """Get operation ID from message content."""
        return self.content.get("operationId", "")

    @property
    def correlation_id(self) -> str:
        """Get correlation ID from message content."""
        return self.content.get("correlationId", "")


class QueueStorageClient:
    """
    Async client for Azure Queue Storage operations.

    Supports both Azure Storage and Azurite for local development.
    """

    # Default visibility timeout in seconds
    DEFAULT_VISIBILITY_TIMEOUT = 30

    # Default message time-to-live in seconds (7 days)
    DEFAULT_TTL = 604800

    def __init__(self, settings: AzureStorageSettings | None = None) -> None:
        """Initialize the queue storage client."""
        self._settings = settings or get_settings().azure_storage
        self._async_client: AsyncQueueServiceClient | None = None
        self._sync_client: QueueServiceClient | None = None

    @property
    def connection_string(self) -> str:
        """Get the connection string."""
        return self._settings.connection_string

    async def _get_async_client(self) -> AsyncQueueServiceClient:
        """Get or create async queue service client."""
        if self._async_client is None:
            if self._settings.account_name:
                self._async_client = AsyncQueueServiceClient(
                    account_url=f"https://{self._settings.account_name}.queue.core.windows.net",
                    credential=get_azure_credential(None, get_settings().azure_client_id or None),
                )
            else:
                self._async_client = AsyncQueueServiceClient.from_connection_string(
                    self.connection_string
                )
        return self._async_client

    def _get_sync_client(self) -> QueueServiceClient:
        """Get or create sync queue service client."""
        if self._sync_client is None:
            if self._settings.account_name:
                self._sync_client = QueueServiceClient(
                    account_url=f"https://{self._settings.account_name}.queue.core.windows.net",
                    credential=get_azure_credential(None, get_settings().azure_client_id or None),
                )
            else:
                self._sync_client = QueueServiceClient.from_connection_string(
                    self.connection_string
                )
        return self._sync_client

    def _get_queue_client(self, client: Any, queue: str):
        """Get a queue client configured for base64-encoded text messages."""
        return client.get_queue_client(
            queue,
            message_encode_policy=TextBase64EncodePolicy(),
            message_decode_policy=TextBase64DecodePolicy(),
        )

    async def close(self) -> None:
        """Close the async client connection."""
        if self._async_client:
            await self._async_client.close()
            self._async_client = None

    def _create_message_envelope(
        self,
        tenant_id: str,
        file_id: str,
        file_version: int = 1,
        payload: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a standard message envelope.

        Args:
            tenant_id: Tenant identifier
            file_id: File identifier
            file_version: File version
            payload: Additional message data
            correlation_id: Optional correlation ID for tracing

        Returns:
            Message envelope dict
        """
        return {
            "tenantId": tenant_id,
            "fileId": file_id,
            "fileVersion": file_version,
            "operationId": str(uuid4()),
            "correlationId": correlation_id or str(uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "retryCount": 0,
            "payload": payload or {},
            "_datadog": self._get_datadog_trace_headers(),
        }

    @staticmethod
    def _get_datadog_trace_headers() -> dict[str, str]:
        """Extract current Datadog trace context for propagation through queues."""
        try:
            from ddtrace import tracer
            from ddtrace.propagation.http import HTTPPropagator

            active_span = tracer.current_span()
            if active_span:
                headers: dict[str, str] = {}
                HTTPPropagator.inject(active_span.context, headers)
                return headers
        except ImportError:
            pass
        return {}

    async def send_message(
        self,
        queue: str,
        tenant_id: str,
        file_id: str,
        file_version: int = 1,
        payload: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        visibility_timeout: int | None = None,
        time_to_live: int | None = None,
    ) -> dict[str, Any]:
        """
        Send a message to a queue.

        Args:
            queue: Queue name
            tenant_id: Tenant identifier
            file_id: File identifier
            file_version: File version
            payload: Additional message data
            correlation_id: Optional correlation ID for tracing
            visibility_timeout: Seconds before message is visible (default 0)
            time_to_live: Seconds before message expires (default 7 days)

        Returns:
            Message metadata including message_id
        """
        client = await self._get_async_client()
        queue_client = self._get_queue_client(client, queue)

        message_content = self._create_message_envelope(
            tenant_id=tenant_id,
            file_id=file_id,
            file_version=file_version,
            payload=payload,
            correlation_id=correlation_id,
        )

        # Log the exact message content being sent for debugging differences
        logging.getLogger(__name__).debug(
            "Sending queue message to '%s': %s", queue, json.dumps(message_content)
        )

        result = await queue_client.send_message(
            json.dumps(message_content),
            visibility_timeout=visibility_timeout,
            time_to_live=time_to_live or self.DEFAULT_TTL,
        )

        return {
            "message_id": result.id,
            "pop_receipt": result.pop_receipt,
            "operation_id": message_content["operationId"],
            "correlation_id": message_content["correlationId"],
        }

    async def send_raw_message(
        self,
        queue: str,
        content: dict[str, Any],
        visibility_timeout: int | None = None,
        time_to_live: int | None = None,
    ) -> dict[str, Any]:
        """
        Send a raw message to a queue (without envelope).

        Args:
            queue: Queue name
            content: Message content as dict
            visibility_timeout: Seconds before message is visible
            time_to_live: Seconds before message expires

        Returns:
            Message metadata
        """
        client = await self._get_async_client()
        queue_client = self._get_queue_client(client, queue)

        result = await queue_client.send_message(
            json.dumps(content),
            visibility_timeout=visibility_timeout,
            time_to_live=time_to_live or self.DEFAULT_TTL,
        )

        return {
            "message_id": result.id,
            "pop_receipt": result.pop_receipt,
        }

    async def receive_messages(
        self,
        queue: str,
        max_messages: int = 1,
        visibility_timeout: int | None = None,
    ) -> list[QueueMessage]:
        """
        Receive messages from a queue.

        Messages become invisible to other consumers for the visibility timeout period.

        Args:
            queue: Queue name
            max_messages: Maximum messages to receive (1-32)
            visibility_timeout: Seconds before messages become visible again

        Returns:
            List of QueueMessage objects
        """
        client = await self._get_async_client()
        queue_client = self._get_queue_client(client, queue)

        messages = []
        async for msg in queue_client.receive_messages(
            messages_per_page=max_messages,
            visibility_timeout=visibility_timeout or self.DEFAULT_VISIBILITY_TIMEOUT,
        ):
            try:
                content = json.loads(msg.content)
            except json.JSONDecodeError:
                content = {"raw": msg.content}

            messages.append(
                QueueMessage(
                    message_id=msg.id,
                    pop_receipt=msg.pop_receipt,
                    content=content,
                    dequeue_count=msg.dequeue_count,
                    inserted_on=msg.inserted_on,
                    expires_on=msg.expires_on,
                )
            )

            if len(messages) >= max_messages:
                break

        return messages

    async def delete_message(self, queue: str, message_id: str, pop_receipt: str) -> bool:
        """
        Delete a message from a queue.

        Args:
            queue: Queue name
            message_id: Message ID
            pop_receipt: Pop receipt from receive

        Returns:
            True if deleted
        """
        client = await self._get_async_client()
        queue_client = self._get_queue_client(client, queue)

        await queue_client.delete_message(message_id, pop_receipt)
        return True

    async def update_message_visibility(
        self,
        queue: str,
        message_id: str,
        pop_receipt: str,
        visibility_timeout: int,
    ) -> str:
        """
        Update message visibility timeout.

        Args:
            queue: Queue name
            message_id: Message ID
            pop_receipt: Current pop receipt
            visibility_timeout: New visibility timeout in seconds

        Returns:
            New pop receipt
        """
        client = await self._get_async_client()
        queue_client = self._get_queue_client(client, queue)

        result = await queue_client.update_message(
            message_id,
            pop_receipt,
            visibility_timeout=visibility_timeout,
        )
        return result.pop_receipt

    async def peek_messages(self, queue: str, max_messages: int = 1) -> list[dict[str, Any]]:
        """
        Peek at messages without making them invisible.

        Args:
            queue: Queue name
            max_messages: Maximum messages to peek (1-32)

        Returns:
            List of message contents
        """
        client = await self._get_async_client()
        queue_client = self._get_queue_client(client, queue)

        messages = []
        peeked = await queue_client.peek_messages(max_messages=max_messages)

        for msg in peeked:
            try:
                content = json.loads(msg.content)
            except json.JSONDecodeError:
                content = {"raw": msg.content}

            messages.append({
                "message_id": msg.id,
                "content": content,
                "inserted_on": msg.inserted_on,
                "expires_on": msg.expires_on,
            })

        return messages

    async def clear_queue(self, queue: str) -> None:
        """
        Clear all messages from a queue.

        Args:
            queue: Queue name
        """
        client = await self._get_async_client()
        queue_client = self._get_queue_client(client, queue)

        await queue_client.clear_messages()

    async def get_queue_properties(self, queue: str) -> dict[str, Any]:
        """
        Get queue properties including approximate message count.

        Args:
            queue: Queue name

        Returns:
            Queue properties dict
        """
        client = await self._get_async_client()
        queue_client = self._get_queue_client(client, queue)

        props = await queue_client.get_queue_properties()
        return {
            "name": queue,
            "approximate_message_count": props.approximate_message_count,
            "metadata": props.metadata,
        }

    async def create_queue_if_not_exists(self, queue: str) -> bool:
        """
        Create a queue if it doesn't exist.

        Args:
            queue: Queue name

        Returns:
            True if created, False if already existed
        """
        client = await self._get_async_client()

        try:
            await client.create_queue(queue)
            return True
        except Exception:
            # Queue already exists
            return False

    def create_queue_if_not_exists_sync(self, queue: str) -> bool:
        """
        Create a queue if it doesn't exist (sync version for setup scripts).

        Args:
            queue: Queue name

        Returns:
            True if created, False if already existed
        """
        client = self._get_sync_client()

        try:
            client.create_queue(queue)
            return True
        except Exception:
            # Queue already exists
            return False
