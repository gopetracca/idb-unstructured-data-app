"""Port interface for embedding generation service."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class EmbeddingResult:
    """Result of an embedding operation."""

    text: str
    vector: list[float]
    token_count: int
    model: str
    dimension: int


class EmbeddingPort(ABC):
    """
    Abstract interface for embedding generation operations.

    This port defines the contract that any embedding implementation
    must fulfill, allowing for both fake (testing) and real (Azure OpenAI)
    implementations.
    """

    @abstractmethod
    async def generate_embeddings(
        self,
        texts: list[str],
        model: str | None = None,
    ) -> list[EmbeddingResult]:
        """
        Generate embeddings for a batch of texts.

        Args:
            texts: List of texts to embed
            model: Embedding model to use (optional, uses default if not specified)

        Returns:
            List of EmbeddingResult with vectors and metadata

        Raises:
            EmbeddingError: If embedding generation fails
            RateLimitError: If rate limit is exceeded
        """
        pass

    @abstractmethod
    def get_supported_models(self) -> list[str]:
        """
        Get list of supported embedding models.

        Returns:
            List of supported model names
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    def count_tokens(self, text: str, model: str | None = None) -> int:
        """
        Count tokens in text for a given model.

        Args:
            text: The text to count tokens for
            model: The model to use for tokenization (optional)

        Returns:
            The number of tokens in the text
        """
        pass

    def is_model_supported(self, model: str) -> bool:
        """
        Check if a model is supported.

        Args:
            model: The model name to check

        Returns:
            True if model is supported, False otherwise
        """
        return model in self.get_supported_models()
