"""Document store port for CRUD operations on documents."""

from typing import Protocol

from src.core.entities.composites import DocumentComplete


class DocumentStorePort(Protocol):
    """Port interface for document CRUD operations.

    Operates on the full DocumentComplete composite (files + pipeline_state + file_metadata).
    Used by upload, update, delete, ingest, and read use cases.
    """

    async def create(self, doc: DocumentComplete) -> DocumentComplete:
        """Create a new document (files + pipeline_state + file_metadata rows)."""
        ...

    async def get_by_id(self, tenant_id: str, file_id: str) -> DocumentComplete | None:
        """Get a document by tenant ID and file ID."""
        ...

    async def update(self, doc: DocumentComplete) -> DocumentComplete:
        """Update an existing document."""
        ...

    async def delete(self, tenant_id: str, file_id: str) -> bool:
        """Delete a document (cascades to pipeline_state, file_metadata, chunks, events)."""
        ...

    async def query_by_tenant(
        self,
        tenant_id: str,
        limit: int | None = None,
    ) -> list[DocumentComplete]:
        """Query all documents for a tenant."""
        ...

    async def count_by_tenant(self, tenant_id: str) -> int:
        """Count all documents for a tenant."""
        ...

    async def query_by_ezshare_id(
        self,
        tenant_id: str,
        ezshare_id: str,
    ) -> DocumentComplete | None:
        """Query for a document by ezshare_id."""
        ...
