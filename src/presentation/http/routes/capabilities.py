"""Capabilities HTTP routes."""

import logging
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Security, status

from src.application.use_cases.chunk_document import ChunkDocumentUseCase
from src.application.use_cases.process_document import ProcessDocumentUseCase
from src.application.use_cases.vectorize_chunks import VectorizeChunksUseCase
from src.container import Container
from src.presentation.http.auth import CurrentUser, get_current_user
from src.presentation.http.schemas.capabilities import (
    CapabilitiesResponse,
    ChunkingStrategyCapability,
    EmbeddingModelCapability,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["capabilities"])


def set_chunk_document_use_case(use_case: ChunkDocumentUseCase) -> None:
    """Set the ChunkDocumentUseCase instance (called during app startup)."""
    global _chunk_use_case
    _chunk_use_case = use_case


def set_vectorize_chunks_use_case(use_case: VectorizeChunksUseCase) -> None:
    """Set the VectorizeChunksUseCase instance (called during app startup)."""
    global _vectorize_use_case
    _vectorize_use_case = use_case


@router.get(
    "/capabilities",
    response_model=CapabilitiesResponse,
    summary="Get pipeline capabilities",
    description="""
    Get the capabilities of the RAG pipeline including supported formats,
    chunking strategies, and embedding models.

    This endpoint consolidates all capability information in one response.
    """,
)
@inject
async def get_capabilities(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=["api.read"])],
    process_use_case: ProcessDocumentUseCase = Depends(
        Provide[Container.process_document_use_case]
    ),
    chunk_use_case: ChunkDocumentUseCase = Depends(Provide[Container.chunk_document_use_case]),
    vectorize_use_case: VectorizeChunksUseCase = Depends(
        Provide[Container.vectorize_chunks_use_case]
    ),
) -> CapabilitiesResponse:
    """
    Get pipeline capabilities.

    Returns:
        CapabilitiesResponse with supported formats, strategies, and models
    """
    try:
        # Get supported formats from document intelligence adapter
        supported_formats = process_use_case._document_intelligence.get_supported_formats()

        # Get chunking strategies from chunker
        strategies = chunk_use_case._chunker.get_supported_strategies()
        chunking_strategies = [
            ChunkingStrategyCapability(
                name=strategy.value,
                parameters=_get_strategy_parameters(strategy.value),
            )
            for strategy in strategies
        ]

        # Get embedding models from embedding port
        embedding_port = vectorize_use_case._embedding_port
        models = embedding_port.get_supported_models()
        embedding_models = [
            EmbeddingModelCapability(
                name=model,
                dimensions=embedding_port.get_model_dimension(model),
            )
            for model in models
        ]

        return CapabilitiesResponse(
            supported_formats=supported_formats,
            chunking_strategies=chunking_strategies,
            embedding_models=embedding_models,
        )

    except Exception as e:
        logger.exception("Error retrieving capabilities")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "InternalServerError",
                "message": f"Failed to retrieve capabilities: {str(e)}",
            },
        )


def _get_strategy_parameters(strategy_name: str) -> list[str]:
    """Get parameter names for a chunking strategy."""
    # Map strategy names to their parameters
    strategy_params = {
        "fixed_size": ["chunkSize", "chunkOverlap"],
        "semantic_chunking": ["maxChunkSize"],
        "markdown_aware": ["maxChunkSize"],
        "recursive_chunking": ["maxChunkSize", "minChunkSize"],
    }
    return strategy_params.get(strategy_name, [])
