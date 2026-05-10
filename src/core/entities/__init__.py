"""Domain entities for the RAG pipeline."""

from src.core.entities.chunk_index import ChunkIndex
from src.core.entities.chunk_metadata_index import ChunkMetadataIndex, EmbeddingStatus
from src.core.entities.composites import DocumentComplete, DocumentWithPipeline
from src.core.entities.document import Document
from src.core.entities.document_analysis import (
    ExtractionMetadata,
    MarkdownOutput,
    PageContent,
)
from src.core.entities.embedding import Embedding, EmbeddingMetadata
from src.core.entities.pipeline_state import OverallStatus, PipelineState, ProcessingStage
from src.core.entities.search_result import SearchResult
from src.core.entities.vector_document import VectorDocument

__all__ = [
    "Document",
    "DocumentComplete",
    "DocumentWithPipeline",
    "PipelineState",
    "ProcessingStage",
    "OverallStatus",
    "ChunkIndex",
    "ChunkMetadataIndex",
    "EmbeddingStatus",
    "ExtractionMetadata",
    "MarkdownOutput",
    "PageContent",
    "Embedding",
    "EmbeddingMetadata",
    "VectorDocument",
    "SearchResult",
]
