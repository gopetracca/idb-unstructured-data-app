"""File index storage port for pipeline-oriented document metadata operations."""

from typing import Protocol

from src.application.dto.file_index_filters import FileIndexFilters
from src.application.ports.metadata_store import MetadataStorePort
from src.core.entities.file_index import FileIndex, OverallStatus, ProcessingStage


class FileIndexStorePort(MetadataStorePort, Protocol):
    """Port interface for file index storage operations used by pipeline use cases."""

    async def close(self) -> None:
        """Close any owned client/session resources."""
        ...

    async def upsert(self, file_index: FileIndex) -> FileIndex:
        """Create or update a file index record."""
        ...

    async def query_by_status(
        self,
        tenant_id: str,
        status: OverallStatus,
        limit: int | None = None,
    ) -> list[FileIndex]:
        """Query files by processing status."""
        ...

    async def query_by_stage(
        self,
        tenant_id: str,
        stage: ProcessingStage,
        limit: int | None = None,
    ) -> list[FileIndex]:
        """Query files by processing stage."""
        ...

    async def query_failed(
        self,
        tenant_id: str,
        limit: int | None = None,
    ) -> list[FileIndex]:
        """Query failed files."""
        ...

    async def query_processing(
        self,
        tenant_id: str,
        limit: int | None = None,
    ) -> list[FileIndex]:
        """Query files currently in processing status."""
        ...

    async def mark_processing(
        self,
        tenant_id: str,
        file_id: str,
        stage: ProcessingStage,
    ) -> FileIndex | None:
        """Mark a file as processing at the given stage."""
        ...

    async def mark_completed(self, tenant_id: str, file_id: str) -> FileIndex | None:
        """Mark a file as completed."""
        ...

    async def mark_failed(
        self,
        tenant_id: str,
        file_id: str,
        error_message: str,
    ) -> FileIndex | None:
        """Mark a file as failed."""
        ...

    async def update_chunk_counts(
        self,
        tenant_id: str,
        file_id: str,
        chunk_count: int,
        embedded_chunk_count: int | None = None,
    ) -> FileIndex | None:
        """Update chunk and optional embedded chunk counts."""
        ...

    async def update_embedded_count(
        self,
        tenant_id: str,
        file_id: str,
        embedded_count: int,
    ) -> FileIndex | None:
        """Update only embedded chunk count."""
        ...

    async def update_blob_references(
        self,
        tenant_id: str,
        file_id: str,
        raw_blob_ref: str | None = None,
        text_blob_ref: str | None = None,
    ) -> FileIndex | None:
        """
        Update blob storage references for a file.

        Args:
            tenant_id: Tenant identifier
            file_id: File identifier
            raw_blob_ref: Optional raw file blob path to update
            text_blob_ref: Optional text file blob path to update

        Returns:
            Updated FileIndex or None if not found
        """
        ...

    async def count_by_status(self, tenant_id: str, status: OverallStatus) -> int:
        """Count files by status."""
        ...

    async def query_with_filters(
        self,
        tenant_id: str,
        filters: FileIndexFilters | None = None,
        max_results: int | None = None,
    ) -> list[FileIndex]:
        """Query files by promoted metadata filters."""
        ...

    async def query_by_operation_number(
        self,
        tenant_id: str,
        operation_number: str,
        max_results: int | None = None,
    ) -> list[FileIndex]:
        """Convenience query by operation number."""
        ...

    async def query_by_sector(
        self,
        tenant_id: str,
        sector: str,
        max_results: int | None = None,
    ) -> list[FileIndex]:
        """Convenience query by sector."""
        ...

    async def query_by_dept_id(
        self,
        tenant_id: str,
        dept_id: str,
        max_results: int | None = None,
    ) -> list[FileIndex]:
        """Convenience query by department ID."""
        ...

    async def query_disclosed_documents(
        self,
        tenant_id: str,
        disclosed: bool = True,
        max_results: int | None = None,
    ) -> list[FileIndex]:
        """Convenience query for disclosed/private documents."""
        ...

    async def count_by_sector(self, tenant_id: str, sector: str) -> int:
        """Count files by sector."""
        ...

    async def count_by_operation_number(
        self,
        tenant_id: str,
        operation_number: str,
    ) -> int:
        """Count files by operation number."""
        ...
