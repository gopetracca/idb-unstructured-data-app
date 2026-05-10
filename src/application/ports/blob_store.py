"""BlobStore port interface for file storage operations."""

from typing import Any, Protocol


class BlobStorePort(Protocol):
    """
    Port interface for blob storage operations.

    This interface defines the contract that any blob storage implementation
    must fulfill for the application layer use cases.
    """

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
        ...

    async def delete(self, container: str, blob_path: str) -> bool:
        """
        Delete a blob from storage.

        Args:
            container: Container/bucket name
            blob_path: Full path to the blob

        Returns:
            True if deleted successfully
        """
        ...

    async def exists(self, container: str, blob_path: str) -> bool:
        """
        Check if a blob exists.

        Args:
            container: Container/bucket name
            blob_path: Full path to the blob

        Returns:
            True if blob exists
        """
        ...

    async def get_properties(self, container: str, blob_path: str) -> dict[str, Any]:
        """
        Get blob properties.

        Args:
            container: Container/bucket name
            blob_path: Full path to the blob

        Returns:
            Dict with blob properties (name, size, content_type, etc.)
        """
        ...

    async def delete_by_prefix(self, container: str, prefix: str) -> int:
        """
        Delete all blobs matching a prefix.

        Args:
            container: Container/bucket name
            prefix: Prefix to match

        Returns:
            Number of blobs deleted
        """
        ...
