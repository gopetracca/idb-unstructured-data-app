"""Unit tests for ChunkingStrategy value object."""

import pytest
from pydantic import ValidationError

from src.core.value_objects.chunking_strategy import ChunkingStrategy, ChunkingStrategyName


class TestChunkingStrategyName:
    """Tests for ChunkingStrategyName enum."""

    def test_fixed_size_value(self):
        """Test fixed_size strategy value."""
        assert ChunkingStrategyName.FIXED_SIZE.value == "fixed_size"

    def test_semantic_value(self):
        """Test semantic strategy value."""
        assert ChunkingStrategyName.SEMANTIC.value == "semantic_chunking"

    def test_markdown_aware_value(self):
        """Test markdown_aware strategy value."""
        assert ChunkingStrategyName.MARKDOWN_AWARE.value == "markdown_aware"

    def test_recursive_value(self):
        """Test recursive strategy value."""
        assert ChunkingStrategyName.RECURSIVE.value == "recursive_chunking"


class TestChunkingStrategy:
    """Tests for ChunkingStrategy value object."""

    def test_create_default_strategy(self):
        """Test creating strategy with default values."""
        strategy = ChunkingStrategy()

        assert strategy.strategy_name == ChunkingStrategyName.FIXED_SIZE
        assert strategy.chunk_size == 512
        assert strategy.chunk_overlap == 50
        assert strategy.respect_sentences is True

    def test_create_custom_strategy(self):
        """Test creating strategy with custom values."""
        strategy = ChunkingStrategy(
            strategy_name=ChunkingStrategyName.SEMANTIC,
            parameters={
                "chunk_size": 1024,
                "chunk_overlap": 100,
            },
        )

        assert strategy.strategy_name == ChunkingStrategyName.SEMANTIC
        assert strategy.chunk_size == 1024
        assert strategy.chunk_overlap == 100

    def test_fixed_size_factory(self):
        """Test fixed_size factory method."""
        strategy = ChunkingStrategy.fixed_size(
            chunk_size=256,
            chunk_overlap=25,
            separator="\n",
        )

        assert strategy.strategy_name == ChunkingStrategyName.FIXED_SIZE
        assert strategy.chunk_size == 256
        assert strategy.chunk_overlap == 25
        assert strategy.separator == "\n"

    def test_semantic_factory(self):
        """Test semantic factory method."""
        strategy = ChunkingStrategy.semantic(
            chunk_size=2048,
            chunk_overlap=200,
            respect_sentences=False,
        )

        assert strategy.strategy_name == ChunkingStrategyName.SEMANTIC
        assert strategy.chunk_size == 2048
        assert strategy.respect_sentences is False

    def test_markdown_aware_factory(self):
        """Test markdown_aware factory method."""
        strategy = ChunkingStrategy.markdown_aware(
            chunk_size=1024,
            respect_code_blocks=True,
            max_header_depth=2,
        )

        assert strategy.strategy_name == ChunkingStrategyName.MARKDOWN_AWARE
        assert strategy.respect_code_blocks is True
        assert strategy.max_header_depth == 2

    def test_recursive_factory(self):
        """Test recursive factory method."""
        strategy = ChunkingStrategy.recursive(
            chunk_size=512,
            separators=["\n\n", "\n", " "],
        )

        assert strategy.strategy_name == ChunkingStrategyName.RECURSIVE
        assert strategy.separators == ["\n\n", "\n", " "]

    def test_recursive_factory_default_separators(self):
        """Test recursive factory with default separators."""
        strategy = ChunkingStrategy.recursive()

        assert strategy.separators == ["\n\n", "\n", ". ", " "]

    def test_chunk_size_validation_min(self):
        """Test chunk_size minimum validation."""
        with pytest.raises(ValidationError):
            ChunkingStrategy(parameters={"chunk_size": 10})  # Below minimum of 50

    def test_chunk_size_validation_max(self):
        """Test chunk_size maximum validation."""
        with pytest.raises(ValidationError):
            ChunkingStrategy(parameters={"chunk_size": 5000})  # Above maximum of 4096

    def test_chunk_overlap_validation_min(self):
        """Test chunk_overlap minimum validation."""
        with pytest.raises(ValidationError):
            ChunkingStrategy(parameters={"chunk_overlap": -1})  # Below minimum of 0

    def test_chunk_overlap_validation_max(self):
        """Test chunk_overlap maximum validation."""
        with pytest.raises(ValidationError):
            ChunkingStrategy(parameters={"chunk_overlap": 600})  # Above maximum of 500

    def test_overlap_less_than_chunk_size(self):
        """Test that overlap must be less than chunk_size."""
        with pytest.raises(ValidationError):
            ChunkingStrategy(
                parameters={"chunk_size": 100, "chunk_overlap": 150}
            )

    def test_model_validate_nested_format(self):
        """Test creating strategy from nested {strategy_name, parameters} format."""
        data = {
            "strategy_name": "semantic_chunking",
            "parameters": {
                "chunk_size": 1024,
                "chunk_overlap": 100,
                "respect_sentences": True,
            },
        }

        strategy = ChunkingStrategy.model_validate(data)

        assert strategy.strategy_name == ChunkingStrategyName.SEMANTIC
        assert strategy.chunk_size == 1024
        assert strategy.chunk_overlap == 100

    def test_model_validate_nested_with_defaults(self):
        """Test creating strategy from minimal nested dictionary."""
        data = {
            "strategy_name": "fixed_size",
            "parameters": {},
        }

        strategy = ChunkingStrategy.model_validate(data)

        assert strategy.strategy_name == ChunkingStrategyName.FIXED_SIZE
        assert strategy.chunk_size == 512  # default

    def test_model_validate_rejects_flat_format(self):
        """Test strict nested shape rejects flat strategy parameters."""
        data = {
            "strategy_name": "semantic_chunking",
            "chunk_size": 1200,
            "chunk_overlap": 80,
            "respect_sentences": False,
        }

        with pytest.raises(ValidationError):
            ChunkingStrategy.model_validate(data)

    def test_model_validate_rejects_wrong_strategy_specific_fields(self):
        """Test strategy-specific fields are validated against selected strategy."""
        data = {
            "strategy_name": "fixed_size",
            "parameters": {
                "chunk_size": 512,
                "chunk_overlap": 50,
                "respect_code_blocks": True,
            },
        }

        with pytest.raises(ValidationError):
            ChunkingStrategy.model_validate(data)

    def test_model_dump(self):
        """Test converting strategy to nested dictionary via model_dump."""
        strategy = ChunkingStrategy.fixed_size(chunk_size=256, chunk_overlap=25)

        result = strategy.model_dump()

        assert result["strategy_name"] == "fixed_size"
        assert result["parameters"]["chunk_size"] == 256
        assert result["parameters"]["chunk_overlap"] == 25

    def test_max_header_depth_validation_min(self):
        """Test max_header_depth minimum validation."""
        with pytest.raises(ValidationError):
            ChunkingStrategy.markdown_aware(max_header_depth=0)

    def test_max_header_depth_validation_max(self):
        """Test max_header_depth maximum validation."""
        with pytest.raises(ValidationError):
            ChunkingStrategy.markdown_aware(max_header_depth=7)
