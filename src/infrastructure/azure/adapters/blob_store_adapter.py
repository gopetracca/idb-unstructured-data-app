"""Adapter that implements BlobStorePort using BlobStorageClient."""

from typing import Any

from src.application.ports.blob_client import BlobClientPort
from src.application.ports.blob_store import BlobStorePort
from src.config.settings import AzureStorageSettings, get_settings
from src.infrastructure.azure.clients.blob_client import BlobStorageClient


class BlobStoreAdapter(BlobStorePort, BlobClientPort):
    """
    Adapter that wraps BlobStorageClient to implement BlobStorePort.

    This adapter maps the port interface methods to the corresponding
    BlobStorageClient methods, enabling clean architecture dependency inversion.
    """

    def __init__(
        self,
        blob_client: BlobStorageClient | None = None,
        settings: AzureStorageSettings | None = None,
    ) -> None:
        """
        Initialize the adapter.

        Args:
            blob_client: Optional BlobStorageClient instance
            settings: Optional AzureStorageSettings instance
        """
        self._settings = settings or get_settings().azure_storage
        self._client = blob_client or BlobStorageClient(self._settings)

    async def upload(
        self,
        container: str,
        blob_path: str,
        data: bytes,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Upload data to blob storage.

        Args:
            container: Container/bucket name
            blob_path: Full path for the blob
            data: File content as bytes
            content_type: MIME type
            metadata: Optional blob-level metadata

        Returns:
            Dict with upload result (etag, last_modified, etc.)
        """
        return await self.upload_blob(
            container=container,
            blob_path=blob_path,
            data=data,
            content_type=content_type,
            overwrite=True,
            metadata=metadata,
        )

    async def upload_blob(
        self,
        container: str,
        blob_path: str,
        data: bytes | str,
        content_type: str = "application/octet-stream",
        overwrite: bool = True,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Upload data to blob storage using client-style semantics."""
        return await self._client.upload_blob(
            container=container,
            blob_path=blob_path,
            data=data,
            content_type=content_type,
            overwrite=overwrite,
            metadata=metadata,
        )

    async def delete(self, container: str, blob_path: str) -> bool:
        """
        Delete a blob from storage.

        Args:
            container: Container/bucket name
            blob_path: Full path to the blob

        Returns:
            True if deleted successfully
        """
        return await self._client.delete_blob(container, blob_path)

    async def exists(self, container: str, blob_path: str) -> bool:
        """
        Check if a blob exists.

        Args:
            container: Container/bucket name
            blob_path: Full path to the blob

        Returns:
            True if blob exists
        """
        return await self.blob_exists(container, blob_path)

    async def blob_exists(self, container: str, blob_path: str) -> bool:
        """Check if a blob exists using client-style semantics."""
        return await self._client.blob_exists(container, blob_path)

    async def delete_blob(self, container: str, blob_path: str) -> bool:
        """Delete a blob using client-style semantics."""
        return await self._client.delete_blob(container, blob_path)

    async def download_blob(self, container: str, blob_path: str) -> bytes:
        """Download blob content."""
        return await self._client.download_blob(container, blob_path)

    async def list_blobs(
        self,
        container: str,
        prefix: str | None = None,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        """List blobs in a container."""
        return await self._client.list_blobs(
            container=container,
            prefix=prefix,
            max_results=max_results,
        )

    async def get_properties(self, container: str, blob_path: str) -> dict[str, Any]:
        """
        Get blob properties.

        Args:
            container: Container/bucket name
            blob_path: Full path to the blob

        Returns:
            Dict with blob properties (name, size, content_type, etc.)
        """
        return await self._client.get_blob_properties(container, blob_path)

    async def delete_by_prefix(self, container: str, prefix: str) -> int:
        """
        Delete all blobs matching a prefix.

        Args:
            container: Container/bucket name
            prefix: Prefix to match

        Returns:
            Number of blobs deleted
        """
        return await self._client.delete_blobs_by_prefix(container, prefix)

    async def create_container_if_not_exists(self, container: str) -> bool:
        """
        Create a container if it doesn't exist.

        Args:
            container: Container name

        Returns:
            True if created, False if already existed
        """
        return await self._client.create_container_if_not_exists(container)

    async def close(self) -> None:
        """Close the underlying client connection."""
        await self._client.close()
