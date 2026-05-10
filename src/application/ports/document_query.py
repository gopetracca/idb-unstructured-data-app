"""Document query port for metadata-based queries."""

from typing import Protocol

from src.application.dto.file_index_filters import FileIndexFilters
from src.core.entities.composites import DocumentComplete


class DocumentQueryPort(Protocol):
    """Port interface for metadata-based document queries.

    Joins files + pipeline_state + file_metadata for rich filtering
    on promoted metadata fields. Used by list and search use cases.
    """

    async def query_with_filters(
        self,
        tenant_id: str,
        filters: FileIndexFilters | None = None,
        max_results: int | None = None,
    ) -> list[DocumentComplete]:
        """Query documents by promoted metadata filters."""
        ...

    async def query_by_operation_number(
        self,
        tenant_id: str,
        operation_number: str,
        max_results: int | None = None,
    ) -> list[DocumentComplete]:
        """Convenience query by operation number."""
        ...

    async def query_by_sector(
        self,
        tenant_id: str,
        sector: str,
        max_results: int | None = None,
    ) -> list[DocumentComplete]:
        """Convenience query by sector."""
        ...

    async def query_by_dept_id(
        self,
        tenant_id: str,
        dept_id: str,
        max_results: int | None = None,
    ) -> list[DocumentComplete]:
        """Convenience query by department ID."""
        ...

    async def query_disclosed_documents(
        self,
        tenant_id: str,
        disclosed: bool = True,
        max_results: int | None = None,
    ) -> list[DocumentComplete]:
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
