"""Unit tests for chunking HTTP schemas."""

import pytest
from pydantic import ValidationError

from src.core.value_objects.chunking_strategy import ChunkingStrategyName
from src.presentation.http.schemas.chunking import UploadChunkingStrategyForm


class TestUploadChunkingStrategyForm:
    """Tests for upload chunking form schema."""

    def test_defaults_to_fixed_size_with_default_parameters(self) -> None:
        """Default form values should build default fixed-size strategy."""
        form = UploadChunkingStrategyForm()

        strategy = form.to_chunking_strategy()

        assert strategy.strategy_name == ChunkingStrategyName.FIXED_SIZE
        assert strategy.chunk_size == 512
        assert strategy.chunk_overlap == 50

    def test_accepts_parameters_json_for_markdown_aware(self) -> None:
        """Valid JSON parameters should be parsed and validated."""
        form = UploadChunkingStrategyForm(
            chunking_strategy_name=ChunkingStrategyName.MARKDOWN_AWARE,
            chunking_parameters=(
                '{"chunk_size": 1200, "chunk_overlap": 100, '
                '"respect_code_blocks": true, "max_header_depth": 4}'
            ),
        )

        strategy = form.to_chunking_strategy()

        assert strategy.strategy_name == ChunkingStrategyName.MARKDOWN_AWARE
        assert strategy.chunk_size == 1200
        assert strategy.chunk_overlap == 100
        assert strategy.respect_code_blocks is True
        assert strategy.max_header_depth == 4

    def test_rejects_invalid_json(self) -> None:
        """Invalid JSON in chunking_parameters should fail validation."""
        with pytest.raises(ValidationError):
            UploadChunkingStrategyForm(chunking_parameters='{"chunk_size": 512,')

    def test_rejects_strategy_mismatch_parameters(self) -> None:
        """Parameters not allowed for selected strategy should fail validation."""
        with pytest.raises(ValidationError):
            UploadChunkingStrategyForm(
                chunking_strategy_name=ChunkingStrategyName.FIXED_SIZE,
                chunking_parameters=(
                    '{"chunk_size": 512, "chunk_overlap": 50, '
                    '"respect_sentences": true}'
                ),
            )
