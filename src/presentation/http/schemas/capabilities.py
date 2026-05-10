"""HTTP schemas for capabilities endpoint."""

from typing import Any

from pydantic import BaseModel, Field


class ChunkingStrategyCapability(BaseModel):
    """Schema for a chunking strategy capability."""

    name: str = Field(..., description="Strategy name")
    parameters: list[str] = Field(..., description="Required parameter names")


class EmbeddingModelCapability(BaseModel):
    """Schema for an embedding model capability."""

    name: str = Field(..., description="Model name")
    dimensions: int = Field(..., ge=1, description="Vector dimensions")


class CapabilitiesResponse(BaseModel):
    """Response schema for capabilities endpoint."""

    supported_formats: list[str] = Field(
        ...,
        description="List of supported MIME types for document upload",
    )
    chunking_strategies: list[ChunkingStrategyCapability] = Field(
        ...,
        description="List of supported chunking strategies with their parameters",
    )
    embedding_models: list[EmbeddingModelCapability] = Field(
        ...,
        description="List of supported embedding models with dimensions",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "supported_formats": [
                        "application/pdf",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        "image/png",
                        "image/jpeg",
                    ],
                    "chunking_strategies": [
                        {
                            "name": "fixed_size",
                            "parameters": ["chunkSize", "chunkOverlap"],
                        }
                    ],
                    "embedding_models": [
                        {
                            "name": "text-embedding-3-small",
                            "dimensions": 1536,
                        },
                        {
                            "name": "text-embedding-3-large",
                            "dimensions": 3072,
                        },
                    ],
                }
            ]
        }
    }
