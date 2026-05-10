"""HTTP schemas for document chunking endpoints."""

import json
from datetime import datetime
from typing import Annotated

from fastapi import Form
from pydantic import BaseModel, Field, model_validator

from src.core.value_objects.chunking_strategy import (
    ChunkingStrategy,
    ChunkingStrategyName,
)


class UploadChunkingStrategyForm(BaseModel):
    """Typed form model for upload endpoint chunking strategy fields."""

    chunking_strategy_name: ChunkingStrategyName = Field(
        default=ChunkingStrategyName.FIXED_SIZE,
        description="Chunking strategy name",
    )
    chunking_parameters: str = Field(
        default='{"chunk_size": 512, "chunk_overlap": 50}',
        description=(
            "JSON object with chunking parameters. "
            "Mandatory keys: chunk_size, chunk_overlap. "
            "Optional keys by strategy: "
            "fixed_size -> separator; "
            "semantic_chunking -> respect_sentences; "
            "markdown_aware -> respect_code_blocks, max_header_depth; "
            "recursive_chunking -> separators."
        ),
        examples=['{"chunk_size": 512, "chunk_overlap": 50}'],
    )

    model_config = {"extra": "forbid"}

    @classmethod
    def as_form(
        cls,
        chunking_strategy_name: Annotated[
            ChunkingStrategyName,
            Form(
                description=(
                    "Chunking strategy: fixed_size, semantic_chunking, "
                    "markdown_aware, recursive_chunking"
                )
            ),
        ] = ChunkingStrategyName.FIXED_SIZE,
        chunking_parameters: Annotated[
            str,
            Form(
                description=(
                    "JSON object with chunking parameters. "
                    'Example: {"chunk_size": 512, "chunk_overlap": 50}. '
                    "Optional keys: separator, separators, respect_sentences, "
                    "respect_code_blocks, max_header_depth."
                ),
                examples=['{"chunk_size": 512, "chunk_overlap": 50}'],
            ),
        ] = '{"chunk_size": 512, "chunk_overlap": 50}',
    ) -> "UploadChunkingStrategyForm":
        """Build the form model from multipart/form-data fields."""
        return cls(
            chunking_strategy_name=chunking_strategy_name,
            chunking_parameters=chunking_parameters,
        )

    @model_validator(mode="after")
    def validate_chunking_parameters(self) -> "UploadChunkingStrategyForm":
        """Validate and normalize the parameters JSON using core strategy validation."""
        _ = self.to_chunking_strategy()
        return self

    def to_chunking_strategy(self) -> ChunkingStrategy:
        """Convert form values into the core ChunkingStrategy model."""
        try:
            parameters = json.loads(self.chunking_parameters)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"chunking_parameters must be valid JSON: {exc.msg}"
            ) from exc

        if not isinstance(parameters, dict):
            raise ValueError("chunking_parameters must be a JSON object")

        return ChunkingStrategy.model_validate(
            {
                "strategy_name": self.chunking_strategy_name.value,
                "parameters": parameters,
            }
        )


class ChunkDocumentRequestSchema(BaseModel):
    """Request schema for document chunking endpoint."""

    file_id: str = Field(..., description="Unique file identifier (UUID)")
    tenant_id: str = Field(default="default", description="Tenant identifier")
    source_container: str = Field(
        default="text",
        description="Source blob container name (contains extracted text)",
    )
    output_container: str = Field(
        default="chunks",
        description="Output blob container name (for chunk storage)",
    )
    chunking_strategy: ChunkingStrategy | None = Field(
        default=None,
        description="Chunking strategy configuration (uses default if not specified)",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "file_id": "550e8400-e29b-41d4-a716-446655440000",
                    "tenant_id": "default",
                    "source_container": "text",
                    "output_container": "chunks",
                    "chunking_strategy": {
                        "strategy_name": "fixed_size",
                        "parameters": {
                            "chunk_size": 512,
                            "chunk_overlap": 50,
                        },
                    },
                }
            ]
        }
    }


class ChunkDocumentResponseSchema(BaseModel):
    """Response schema for document chunking endpoint."""

    file_id: str = Field(..., description="Unique file identifier")
    status: str = Field(..., description="Processing status")
    chunk_count: int = Field(..., ge=0, description="Number of chunks created")
    chunks_url: str | None = Field(
        default=None,
        description="URL to the chunks output directory",
    )
    chunking_strategy: str = Field(
        ...,
        description="Chunking strategy used",
    )
    correlation_id: str = Field(..., description="Correlation ID for tracing")
    processing_time_ms: int | None = Field(
        default=None,
        description="Processing time in milliseconds",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp of response creation",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "file_id": "550e8400-e29b-41d4-a716-446655440000",
                    "status": "completed",
                    "chunk_count": 25,
                    "chunks_url": "chunks/550e8400-e29b-41d4-a716-446655440000/chunks/",
                    "chunking_strategy": "fixed_size",
                    "correlation_id": "abc-123-def",
                    "processing_time_ms": 1250,
                    "created_at": "2026-01-28T10:00:00Z",
                }
            ]
        }
    }


class ChunkSchema(BaseModel):
    """Schema for a single chunk in list response."""

    chunk_id: str = Field(..., description="Unique chunk identifier")
    chunk_index: int = Field(..., ge=0, description="Position in file (0-based)")
    text_preview: str = Field(..., description="Preview of chunk text (first 100 chars)")
    char_count: int = Field(..., ge=0, description="Character count")
    start_char: int = Field(..., ge=0, description="Start position in source")
    end_char: int = Field(..., ge=0, description="End position in source")
    page_number: int | None = Field(default=None, description="Source page number")


class PaginationSchema(BaseModel):
    """Schema for pagination information."""

    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, description="Items per page")
    total_pages: int = Field(..., ge=0, description="Total number of pages")


class ListChunksResponseSchema(BaseModel):
    """Response schema for list chunks endpoint."""

    file_id: str = Field(..., description="File identifier")
    chunk_count: int = Field(..., ge=0, description="Total number of chunks")
    chunks: list[ChunkSchema] = Field(
        default_factory=list,
        description="List of chunks",
    )
    pagination: PaginationSchema = Field(..., description="Pagination information")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "file_id": "550e8400-e29b-41d4-a716-446655440000",
                    "chunk_count": 25,
                    "chunks": [
                        {
                            "chunk_id": "550e8400-e29b-41d4-a716-446655440000_chunk_0",
                            "chunk_index": 0,
                            "text_preview": "This is the beginning of the document...",
                            "char_count": 512,
                            "start_char": 0,
                            "end_char": 512,
                            "page_number": 1,
                        }
                    ],
                    "pagination": {
                        "page": 1,
                        "page_size": 20,
                        "total_pages": 2,
                    },
                }
            ]
        }
    }
