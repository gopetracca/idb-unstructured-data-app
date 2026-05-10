"""Azure Blob Storage client for file operations."""

import asyncio
from typing import Any

from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.storage.blob.aio import BlobServiceClient as AsyncBlobServiceClient

from src.config.settings import AzureStorageSettings, get_settings
from src.infrastructure.azure.clients.credentials import get_azure_credential


class BlobStorageClient:
    """
    Async client for Azure Blob Storage operations.

    Supports both Azure Storage and Azurite for local development.
    """

    def __init__(self, settings: AzureStorageSettings | None = None) -> None:
        """Initialize the blob storage client."""
        self._settings = settings or get_settings().azure_storage
        self._async_client: AsyncBlobServiceClient | None = None
        self._sync_client: BlobServiceClient | None = None

    @property
    def connection_string(self) -> str:
        """Get the connection string."""
        return self._settings.connection_string

    async def _get_async_client(self) -> AsyncBlobServiceClient:
        """Get or create async blob service client."""
        if self._async_client is None:
            kwargs = {
                "max_block_size": 8 * 1024 * 1024,       # 8MB blocks (default: 4MB)
                "max_single_put_size": 16 * 1024 * 1024,  # files ≤ 16MB go as single PUT
            }
            if self._settings.account_name:
                self._async_client = AsyncBlobServiceClient(
                    account_url=f"https://{self._settings.account_name}.blob.core.windows.net",
                    credential=get_azure_credential(None, get_settings().azure_client_id or None),
                    **kwargs,
                )
            else:
                self._async_client = AsyncBlobServiceClient.from_connection_string(
                    self.connection_string,
                    **kwargs,
                )
        return self._async_client

    def _get_sync_client(self) -> BlobServiceClient:
        """Get or create sync blob service client."""
        if self._sync_client is None:
            if self._settings.account_name:
                self._sync_client = BlobServiceClient(
                    account_url=f"https://{self._settings.account_name}.blob.core.windows.net",
                    credential=get_azure_credential(None, get_settings().azure_client_id or None),
                )
            else:
                self._sync_client = BlobServiceClient.from_connection_string(
                    self.connection_string
                )
        return self._sync_client

    async def close(self) -> None:
        """Close the async client connection."""
        if self._async_client:
            await self._async_client.close()
            self._async_client = None

    async def upload_blob(
        self,
        container: str,
        blob_path: str,
        data: bytes | str,
        content_type: str = "application/octet-stream",
        overwrite: bool = True,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Upload data to a blob.

        Args:
            container: Container name
            blob_path: Full blob path (e.g., "file_id/filename.txt")
            data: Content to upload
            content_type: MIME type
            overwrite: Whether to overwrite existing blob
            metadata: Optional blob metadata

        Returns:
            Dict with blob properties including etag and last_modified
        """
        client = await self._get_async_client()
        blob_client = client.get_blob_client(container=container, blob=blob_path)

        content_settings = ContentSettings(content_type=content_type)

        if isinstance(data, str):
            data = data.encode("utf-8")

        result = await blob_client.upload_blob(
            data,
            overwrite=overwrite,
            content_settings=content_settings,
            metadata=metadata,
            max_concurrency=4,
        )

        return {
            "etag": result.get("etag"),
            "last_modified": result.get("last_modified"),
            "container": container,
            "blob_path": blob_path,
        }

    async def download_blob(self, container: str, blob_path: str) -> bytes:
        """
        Download blob content.

        Args:
            container: Container name
            blob_path: Full blob path

        Returns:
            Blob content as bytes
        """
        client = await self._get_async_client()
        blob_client = client.get_blob_client(container=container, blob=blob_path)

        download = await blob_client.download_blob()
        return await download.readall()

    async def download_blob_to_text(self, container: str, blob_path: str) -> str:
        """
        Download blob content as text.

        Args:
            container: Container name
            blob_path: Full blob path

        Returns:
            Blob content as string
        """
        content = await self.download_blob(container, blob_path)
        return content.decode("utf-8")

    async def delete_blob(self, container: str, blob_path: str) -> bool:
        """
        Delete a blob.

        Args:
            container: Container name
            blob_path: Full blob path

        Returns:
            True if deleted successfully
        """
        client = await self._get_async_client()
        blob_client = client.get_blob_client(container=container, blob=blob_path)

        await blob_client.delete_blob()
        return True

    async def blob_exists(self, container: str, blob_path: str) -> bool:
        """
        Check if a blob exists.

        Args:
            container: Container name
            blob_path: Full blob path

        Returns:
            True if blob exists
        """
        client = await self._get_async_client()
        blob_client = client.get_blob_client(container=container, blob=blob_path)

        return await blob_client.exists()

    async def list_blobs(
        self,
        container: str,
        prefix: str | None = None,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        List blobs in a container.

        Args:
            container: Container name
            prefix: Optional prefix to filter blobs
            max_results: Maximum number of results

        Returns:
            List of blob properties
        """
        client = await self._get_async_client()
        container_client = client.get_container_client(container)

        blobs = []
        count = 0

        async for blob in container_client.list_blobs(name_starts_with=prefix):
            blobs.append({
                "name": blob.name,
                "size": blob.size,
                "content_type": blob.content_settings.content_type if blob.content_settings else None,
                "last_modified": blob.last_modified,
                "etag": blob.etag,
                "metadata": blob.metadata,
            })
            count += 1
            if max_results and count >= max_results:
                break

        return blobs

    async def get_blob_properties(self, container: str, blob_path: str) -> dict[str, Any]:
        """
        Get blob properties.

        Args:
            container: Container name
            blob_path: Full blob path

        Returns:
            Dict with blob properties
        """
        client = await self._get_async_client()
        blob_client = client.get_blob_client(container=container, blob=blob_path)

        props = await blob_client.get_blob_properties()
        return {
            "name": props.name,
            "size": props.size,
            "content_type": props.content_settings.content_type if props.content_settings else None,
            "last_modified": props.last_modified,
            "etag": props.etag,
            "metadata": props.metadata,
            "creation_time": props.creation_time,
        }

    async def create_container_if_not_exists(self, container: str) -> bool:
        """
        Create a container if it doesn't exist.

        Args:
            container: Container name

        Returns:
            True if created, False if already existed
        """
        client = await self._get_async_client()
        container_client = client.get_container_client(container)

        try:
            await container_client.create_container()
            return True
        except Exception:
            # Container already exists
            return False

    def create_container_if_not_exists_sync(self, container: str) -> bool:
        """
        Create a container if it doesn't exist (sync version for setup scripts).

        Args:
            container: Container name

        Returns:
            True if created, False if already existed
        """
        client = self._get_sync_client()
        container_client = client.get_container_client(container)

        try:
            container_client.create_container()
            return True
        except Exception:
            # Container already exists
            return False

    async def delete_blobs_by_prefix(self, container: str, prefix: str) -> int:
        """
        Delete all blobs matching a prefix.

        Args:
            container: Container name
            prefix: Prefix to match

        Returns:
            Number of blobs deleted
        """
        blobs = await self.list_blobs(container, prefix=prefix)
        deleted_count = 0

        for blob in blobs:
            await self.delete_blob(container, blob["name"])
            deleted_count += 1

        return deleted_count
