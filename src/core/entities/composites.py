"""Composite entities for use cases that need data from multiple tables.

These are read-side views — not mapped to their own SQL tables.
They compose the three core entities for use cases that need cross-cutting data.
"""

from pydantic import BaseModel

from src.core.entities.document import Document
from src.core.entities.pipeline_state import PipelineState
from src.core.value_objects.document_metadata import DocumentMetadata


class DocumentWithPipeline(BaseModel):
    """Document identity + processing state.

    Used by pipeline use cases (process, chunk, vectorize) that need
    both blob references from Document and state transitions from PipelineState.
    """

    document: Document
    pipeline: PipelineState


class DocumentComplete(BaseModel):
    """Full document view: identity + processing state + metadata.

    Used by CRUD and query use cases (list, get, upload, update, ingest)
    that need the complete picture across all three tables.
    """

    document: Document
    pipeline: PipelineState
    metadata: DocumentMetadata
