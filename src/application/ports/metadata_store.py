"""MetadataStore port interface for document metadata operations."""

from typing import Protocol

from src.core.entities.file_index import FileIndex


class MetadataStorePort(Protocol):
    """
    Port interface for document metadata storage operations.

    This interface defines the contract that any metadata storage implementation
    must fulfill for the application layer use cases.
    """

    async def create(self, file_index: FileIndex) -> FileIndex:
        """
        Create a new file index record.

        Args:
            file_index: FileIndex entity to create

        Returns:
            Created FileIndex entity
        """
        ...

    async def get_by_id(self, tenant_id: str, file_id: str) -> FileIndex | None:
        """
        Get a file index by tenant ID and file ID.

        Args:
            tenant_id: Tenant identifier
            file_id: File identifier

        Returns:
            FileIndex entity or None if not found
        """
        ...

    async def update(self, file_index: FileIndex) -> FileIndex:
        """
        Update an existing file index record.

        Args:
            file_index: FileIndex entity with updated values

        Returns:
            Updated FileIndex entity
        """
        ...

    async def delete(self, tenant_id: str, file_id: str) -> bool:
        """
        Delete a file index record.

        Args:
            tenant_id: Tenant identifier
            file_id: File identifier

        Returns:
            True if deleted
        """
        ...

    async def query_by_tenant(
        self,
        tenant_id: str,
        limit: int | None = None,
    ) -> list[FileIndex]:
        """
        Query all files for a tenant.

        Args:
            tenant_id: Tenant identifier
            limit: Maximum number of results

        Returns:
            List of FileIndex entities
        """
        ...

    async def count_by_tenant(self, tenant_id: str) -> int:
        """
        Count all files for a tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Number of files
        """
        ...

    async def query_by_ezshare_id(
        self,
        tenant_id: str,
        ezshare_id: str,
    ) -> FileIndex | None:
        """
        Query for a file by ezshare_id.

        Args:
            tenant_id: Tenant identifier
            ezshare_id: External document ID

        Returns:
            FileIndex entity or None if not found
        """
        ...
