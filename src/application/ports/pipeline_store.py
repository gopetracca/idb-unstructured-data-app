"""Pipeline store port for processing state transitions."""

from typing import Protocol

from src.core.entities.composites import DocumentWithPipeline
from src.core.entities.document import ReplacedBlobReferences
from src.core.entities.pipeline_state import OverallStatus, PipelineState, ProcessingStage


class PipelineStorePort(Protocol):
    """Port interface for pipeline state operations.

    Operates on the PipelineState entity (pipeline_state table) and
    DocumentWithPipeline composite (files + pipeline_state).
    Used by pipeline use cases (process, chunk, vectorize).
    """

    async def get_by_id(
        self, tenant_id: str, file_id: str
    ) -> DocumentWithPipeline | None:
        """Get document with pipeline state by tenant ID and file ID."""
        ...

    async def mark_processing(
        self,
        tenant_id: str,
        file_id: str,
        stage: ProcessingStage,
    ) -> PipelineState | None:
        """Mark a file as processing at the given stage."""
        ...

    async def mark_completed(self, tenant_id: str, file_id: str) -> PipelineState | None:
        """Mark a file as completed."""
        ...

    async def mark_failed(
        self,
        tenant_id: str,
        file_id: str,
        error_message: str,
    ) -> PipelineState | None:
        """Mark a file as failed."""
        ...

    async def update_chunk_counts(
        self,
        tenant_id: str,
        file_id: str,
        chunk_count: int,
        embedded_chunk_count: int | None = None,
    ) -> PipelineState | None:
        """Update chunk and optional embedded chunk counts."""
        ...

    async def update_embedded_count(
        self,
        tenant_id: str,
        file_id: str,
        embedded_count: int,
    ) -> PipelineState | None:
        """Update only embedded chunk count."""
        ...

    async def update_blob_references(
        self,
        tenant_id: str,
        file_id: str,
        raw_blob_ref: str | None = None,
        text_blob_ref: str | None = None,
        analysis_blob_ref: str | None = None,
        clear_analysis_blob_ref: bool = False,
    ) -> ReplacedBlobReferences:
        """Update blob storage references for a file (on the files table).

        Returns the references this update overwrote, so the caller can clean up exactly
        what it displaced. Reading them beforehand is not equivalent: a concurrent
        extraction of the same document may publish in between, and then both runs would
        sweep the same outputs and neither would sweep the loser's.

        A `None` reference means "leave it alone", so re-running a stage cannot wipe a
        path it did not produce. Clearing is therefore explicit: pass
        `clear_analysis_blob_ref=True` when a run deliberately produced no raw analysis,
        so the row cannot keep pointing at an earlier run's sidecar.
        """
        ...

    async def query_by_status(
        self,
        tenant_id: str,
        status: OverallStatus,
        limit: int | None = None,
    ) -> list[DocumentWithPipeline]:
        """Query files by processing status."""
        ...

    async def query_by_stage(
        self,
        tenant_id: str,
        stage: ProcessingStage,
        limit: int | None = None,
    ) -> list[DocumentWithPipeline]:
        """Query files by processing stage."""
        ...

    async def query_failed(
        self,
        tenant_id: str,
        limit: int | None = None,
    ) -> list[DocumentWithPipeline]:
        """Query failed files."""
        ...

    async def query_processing(
        self,
        tenant_id: str,
        limit: int | None = None,
    ) -> list[DocumentWithPipeline]:
        """Query files currently in processing status."""
        ...

    async def count_by_status(self, tenant_id: str, status: OverallStatus) -> int:
        """Count files by status."""
        ...
