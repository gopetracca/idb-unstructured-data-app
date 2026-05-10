"""Chunking strategy value object."""

from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_serializer, model_validator


class ChunkingStrategyName(StrEnum):
    """Available chunking strategies."""

    FIXED_SIZE = "fixed_size"
    SEMANTIC = "semantic_chunking"
    MARKDOWN_AWARE = "markdown_aware"
    RECURSIVE = "recursive_chunking"


class BaseChunkingParameters(BaseModel):
    """Base parameter model shared by all strategies."""

    chunk_size: int = Field(
        default=512,
        ge=50,
        le=4096,
        description="Target chunk size in characters",
    )
    chunk_overlap: int = Field(
        default=50,
        ge=0,
        le=500,
        description="Overlap between consecutive chunks",
    )

    model_config = {"extra": "forbid"}

    @field_validator("chunk_overlap")
    @classmethod
    def validate_overlap(cls, value: int, info: ValidationInfo) -> int:
        """Ensure overlap is strictly lower than chunk size."""
        chunk_size = info.data.get("chunk_size", 512)
        if value >= chunk_size:
            raise ValueError(
                f"chunk_overlap ({value}) must be less than chunk_size ({chunk_size})"
            )
        return value


class FixedSizeParameters(BaseChunkingParameters):
    """Parameters for fixed-size chunking."""

    separator: str | None = Field(
        default=None,
        description="Optional separator for fixed-size chunking",
    )


class SemanticParameters(BaseChunkingParameters):
    """Parameters for semantic chunking."""

    chunk_size: int = Field(
        default=1024,
        ge=50,
        le=4096,
        description="Target chunk size in characters",
    )
    respect_sentences: bool = Field(
        default=True,
        description="Try to keep sentences intact",
    )


class MarkdownAwareParameters(BaseChunkingParameters):
    """Parameters for markdown-aware chunking."""

    chunk_size: int = Field(
        default=1024,
        ge=50,
        le=4096,
        description="Target chunk size in characters",
    )
    respect_code_blocks: bool = Field(
        default=True,
        description="Keep code blocks intact",
    )
    max_header_depth: int = Field(
        default=3,
        ge=1,
        le=6,
        description="Maximum markdown header depth to track",
    )


class RecursiveParameters(BaseChunkingParameters):
    """Parameters for recursive chunking."""

    separators: list[str] = Field(
        default_factory=lambda: ["\n\n", "\n", ". ", " "],
        description="Separators in priority order",
    )


ChunkingParameters = (
    FixedSizeParameters
    | SemanticParameters
    | MarkdownAwareParameters
    | RecursiveParameters
)


_STRATEGY_PARAMETERS_MODEL: dict[
    ChunkingStrategyName, type[BaseChunkingParameters]
] = {
    ChunkingStrategyName.FIXED_SIZE: FixedSizeParameters,
    ChunkingStrategyName.SEMANTIC: SemanticParameters,
    ChunkingStrategyName.MARKDOWN_AWARE: MarkdownAwareParameters,
    ChunkingStrategyName.RECURSIVE: RecursiveParameters,
}

class ChunkingStrategy(BaseModel):
    """
    Value object representing a chunking strategy configuration.

    Expected shape:
    - {"strategy_name": "...", "parameters": {...}}
    """

    strategy_name: ChunkingStrategyName = Field(
        default=ChunkingStrategyName.FIXED_SIZE,
        description="Name of the chunking strategy",
    )
    parameters: ChunkingParameters = Field(
        default_factory=FixedSizeParameters,
        description="Typed parameters for the selected strategy",
    )

    model_config = {"extra": "forbid"}

    @property
    def chunk_size(self) -> int:
        return self.parameters.chunk_size

    @property
    def chunk_overlap(self) -> int:
        return self.parameters.chunk_overlap

    @property
    def separator(self) -> str | None:
        if isinstance(self.parameters, FixedSizeParameters):
            return self.parameters.separator
        return None

    @property
    def separators(self) -> list[str] | None:
        if isinstance(self.parameters, RecursiveParameters):
            return self.parameters.separators
        return None

    @property
    def respect_sentences(self) -> bool:
        if isinstance(self.parameters, SemanticParameters):
            return self.parameters.respect_sentences
        return True

    @property
    def respect_code_blocks(self) -> bool:
        if isinstance(self.parameters, MarkdownAwareParameters):
            return self.parameters.respect_code_blocks
        return True

    @property
    def max_header_depth(self) -> int:
        if isinstance(self.parameters, MarkdownAwareParameters):
            return self.parameters.max_header_depth
        return 3

    @classmethod
    def fixed_size(
        cls,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        separator: str | None = None,
    ) -> "ChunkingStrategy":
        """Create a fixed-size chunking strategy."""
        return cls(
            strategy_name=ChunkingStrategyName.FIXED_SIZE,
            parameters=FixedSizeParameters(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separator=separator,
            ),
        )

    @classmethod
    def semantic(
        cls,
        chunk_size: int = 1024,
        chunk_overlap: int = 50,
        respect_sentences: bool = True,
    ) -> "ChunkingStrategy":
        """Create a semantic chunking strategy."""
        return cls(
            strategy_name=ChunkingStrategyName.SEMANTIC,
            parameters=SemanticParameters(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                respect_sentences=respect_sentences,
            ),
        )

    @classmethod
    def markdown_aware(
        cls,
        chunk_size: int = 1024,
        chunk_overlap: int = 50,
        respect_code_blocks: bool = True,
        max_header_depth: int = 3,
    ) -> "ChunkingStrategy":
        """Create a markdown-aware chunking strategy."""
        return cls(
            strategy_name=ChunkingStrategyName.MARKDOWN_AWARE,
            parameters=MarkdownAwareParameters(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                respect_code_blocks=respect_code_blocks,
                max_header_depth=max_header_depth,
            ),
        )

    @classmethod
    def recursive(
        cls,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        separators: list[str] | None = None,
    ) -> "ChunkingStrategy":
        """Create a recursive chunking strategy."""
        return cls(
            strategy_name=ChunkingStrategyName.RECURSIVE,
            parameters=RecursiveParameters(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separators=separators or ["\n\n", "\n", ". ", " "],
            ),
        )

    @model_validator(mode="before")
    @classmethod
    def normalize_payload(cls, data: Any) -> Any:
        """Normalize nested input and enforce strategy-specific parameters."""
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        strategy_raw = normalized.get("strategy_name", ChunkingStrategyName.FIXED_SIZE.value)

        try:
            strategy_name = ChunkingStrategyName(strategy_raw)
        except ValueError:
            # Let regular field validation return a clear enum error
            return normalized

        parameters_data: dict[str, Any]
        raw_parameters = normalized.get("parameters") or {}
        if isinstance(raw_parameters, BaseChunkingParameters):
            parameters_data = raw_parameters.model_dump(
                mode="python",
                exclude_unset=True,
                exclude_none=True,
            )
        elif not isinstance(raw_parameters, dict):
            raise ValueError("parameters must be an object")
        else:
            parameters_data = dict(raw_parameters)

        parameter_model = _STRATEGY_PARAMETERS_MODEL[strategy_name]
        normalized["strategy_name"] = strategy_name
        normalized["parameters"] = parameter_model.model_validate(parameters_data)
        return normalized

    @model_validator(mode="after")
    def validate_parameter_type_matches_strategy(self) -> Self:
        """Ensure parsed parameter model matches selected strategy."""
        expected_model = _STRATEGY_PARAMETERS_MODEL[self.strategy_name]
        if not isinstance(self.parameters, expected_model):
            raise ValueError(
                f"Parameters for strategy '{self.strategy_name.value}' "
                f"must be of type {expected_model.__name__}"
            )
        return self

    @model_serializer
    def serialize_model(self) -> dict[str, Any]:
        """Serialize to a compact nested shape for queue payloads and APIs."""
        parameters = self.parameters.model_dump(exclude_unset=True, exclude_none=True)
        if parameters:
            return {
                "strategy_name": self.strategy_name.value,
                "parameters": parameters,
            }
        return {"strategy_name": self.strategy_name.value}
