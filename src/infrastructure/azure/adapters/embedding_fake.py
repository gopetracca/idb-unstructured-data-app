"""Fake embeddings adapter for local development and testing."""

import asyncio
import logging
import random
from hashlib import sha256

from src.application.ports.embedding import EmbeddingPort, EmbeddingResult
from src.core.errors import EmbeddingError

logger = logging.getLogger(__name__)


# Model configurations (same as real adapter)
MODEL_CONFIGS = {
    "text-embedding-3-small": {"dimension": 1536},
    "text-embedding-3-large": {"dimension": 3072},
}


class FakeEmbeddings(EmbeddingPort):
    """
    Fake implementation of EmbeddingPort for local development and testing.

    This adapter generates deterministic fake embeddings based on text content
    without requiring Azure OpenAI resources. Useful for:
    - Local development without API access
    - Unit testing with predictable results
    - Integration testing without incurring API costs
    """

    def __init__(
        self,
        simulated_delay_seconds: float = 0.1,
        default_model: str = "text-embedding-3-small",
    ) -> None:
        """
        Initialize the fake adapter.

        Args:
            simulated_delay_seconds: Delay to simulate API latency
            default_model: Default embedding model to use
        """
        self._delay = simulated_delay_seconds
        self._default_model = default_model

    async def generate_embeddings(
        self,
        texts: list[str],
        model: str | None = None,
    ) -> list[EmbeddingResult]:
        """
        Generate deterministic fake embeddings.

        The embeddings are generated from text hashes, making them:
        - Deterministic: same text always produces same embedding
        - Normalized: vectors have unit length
        - Dimension-aware: respects model's dimension setting

        Args:
            texts: List of texts to embed
            model: Embedding model to use (optional, uses default)

        Returns:
            List of EmbeddingResult with fake vectors and metadata

        Raises:
            EmbeddingError: If model is not supported
        """
        model = model or self._default_model

        if not self.is_model_supported(model):
            raise EmbeddingError(
                message=f"Unsupported embedding model: {model}",
                model=model,
                details={"supported_models": self.get_supported_models()},
            )

        # Simulate API delay
        if self._delay > 0:
            await asyncio.sleep(self._delay)

        dimension = self.get_model_dimension(model)
        results = []

        for text in texts:
            # Generate deterministic vector based on text hash
            vector = self._generate_deterministic_vector(text, dimension)
            token_count = self.count_tokens(text, model)

            results.append(
                EmbeddingResult(
                    text=text,
                    vector=vector,
                    token_count=token_count,
                    model=model,
                    dimension=dimension,
                )
            )

        logger.info(f"Generated {len(results)} fake embeddings using {model}")
        return results

    def _generate_deterministic_vector(self, text: str, dimension: int) -> list[float]:
        """
        Generate deterministic vector from text hash.

        Uses SHA-256 hash as seed for reproducible random number generation.
        The resulting vector is normalized to unit length.

        Args:
            text: Source text for embedding
            dimension: Vector dimension

        Returns:
            Normalized embedding vector
        """
        # Use text hash as seed for reproducibility
        text_hash = sha256(text.encode()).hexdigest()
        seed = int(text_hash[:8], 16)
        rng = random.Random(seed)

        # Generate vector with gaussian distribution
        vector = [rng.gauss(0, 1) for _ in range(dimension)]

        # Normalize to unit length
        magnitude = sum(v * v for v in vector) ** 0.5
        if magnitude > 0:
            vector = [v / magnitude for v in vector]

        return vector

    def get_supported_models(self) -> list[str]:
        """Get list of supported embedding models."""
        return list(MODEL_CONFIGS.keys())

    def get_model_dimension(self, model: str) -> int:
        """
        Get the vector dimension for a model.

        Args:
            model: The model name

        Returns:
            The vector dimension for the model

        Raises:
            EmbeddingError: If model is not supported
        """
        if model not in MODEL_CONFIGS:
            raise EmbeddingError(
                message=f"Unknown model: {model}",
                model=model,
            )
        return MODEL_CONFIGS[model]["dimension"]

    def count_tokens(self, text: str, model: str | None = None) -> int:
        """
        Estimate token count (rough approximation).

        Uses a simple heuristic of ~4 characters per token.
        For production use, the real adapter uses tiktoken for accuracy.

        Args:
            text: The text to count tokens for
            model: The model (unused in fake implementation)

        Returns:
            Estimated number of tokens
        """
        # Simple approximation: ~4 characters per token
        return max(1, len(text) // 4)
