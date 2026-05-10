"""Azure Storage initialization utilities.

This module provides functions to initialize Azure Storage resources
(containers and queues) at application startup.
"""

import logging

from src.config.settings import get_settings
from src.infrastructure.azure.clients.blob_client import BlobStorageClient

logger = logging.getLogger(__name__)


async def initialize_storage(blob_client: BlobStorageClient | None = None) -> None:
    """
    Initialize Azure Storage resources (containers and queues).

    Creates containers and queues if they don't exist.
    This is safe to call multiple times.

    Args:
        blob_client: Optional BlobStorageClient instance. If not provided, a new one will be created.
    """
    from src.infrastructure.azure.clients.queue_client import QueueStorageClient

    settings = get_settings()

    logger.info("Initializing Azure Storage resources")

    # Initialize blob containers
    owns_blob_client = blob_client is None
    if blob_client is None:
        blob_client = BlobStorageClient(settings=settings.azure_storage)

    try:
        for container in settings.azure_storage.container_names:
            try:
                await blob_client.create_container_if_not_exists(container)
                logger.info(f"Ensured container exists: {container}")
            except Exception as e:
                logger.warning(f"Could not create container {container}: {e}")
    finally:
        if owns_blob_client:
            await blob_client.close()

    # Initialize queues
    queue_client = QueueStorageClient(settings.azure_storage)
    try:
        for queue in settings.azure_storage.queue_names:
            try:
                await queue_client.create_queue_if_not_exists(queue)
                logger.info(f"Ensured queue exists: {queue}")
            except Exception as e:
                logger.warning(f"Could not create queue {queue}: {e}")
    finally:
        await queue_client.close()
