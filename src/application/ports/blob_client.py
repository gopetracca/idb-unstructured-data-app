"""Blob client port for low-level blob IO operations."""

from typing import Any, Protocol


class BlobClientPort(Protocol):
    """Port interface for low-level blob operations used by pipeline stages."""

    async def upload_blob(
        self,
        container: str,
        blob_path: str,
        data: bytes | str,
        content_type: str = "application/octet-stream",
        overwrite: bool = True,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Upload data to blob storage."""
        ...

    async def download_blob(self, container: str, blob_path: str) -> bytes:
        """Download blob content."""
        ...

    async def blob_exists(self, container: str, blob_path: str) -> bool:
        """Check if a blob exists."""
        ...

    async def list_blobs(
        self,
        container: str,
        prefix: str | None = None,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        """List blobs in a container."""
        ...
