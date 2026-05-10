"""Azure OpenAI embeddings adapter implementing EmbeddingPort."""

import asyncio
import logging

import tiktoken
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AsyncAzureOpenAI
from openai import RateLimitError as OpenAIRateLimitError

from src.application.ports.embedding import EmbeddingPort, EmbeddingResult
from src.config.settings import EmbeddingSettings, get_settings
from src.core.errors import EmbeddingError, RateLimitError

logger = logging.getLogger(__name__)


# Model configurations
MODEL_CONFIGS = {
    "text-embedding-3-small": {"dimension": 1536, "max_tokens": 8191},
    "text-embedding-3-large": {"dimension": 3072, "max_tokens": 8191},
}


class AzureOpenAIEmbeddings(EmbeddingPort):
    """
    Azure OpenAI implementation of EmbeddingPort.

    Uses the Azure OpenAI service to generate embeddings for text content.
    Includes retry logic with exponential backoff for rate limit handling.
    """

    def __init__(
        self,
        settings: EmbeddingSettings | None = None,
    ) -> None:
        """
        Initialize the Azure OpenAI adapter.

        Args:
            settings: Optional EmbeddingSettings instance
        """
        self._settings = settings or get_settings().embedding
        if self._settings.api_key:
            self._client = AsyncAzureOpenAI(
                azure_endpoint=self._settings.endpoint,
                api_key=self._settings.api_key,
                api_version=self._settings.api_version,
            )
        else:
            azure_client_id = get_settings().azure_client_id
            credential = (
                DefaultAzureCredential(managed_identity_client_id=azure_client_id)
                if azure_client_id
                else DefaultAzureCredential()
            )
            token_provider = get_bearer_token_provider(
                credential,
                "https://cognitiveservices.azure.com/.default",
            )
            self._client = AsyncAzureOpenAI(
                azure_endpoint=self._settings.endpoint,
                azure_ad_token_provider=token_provider,
                api_version=self._settings.api_version,
            )
        # Use cl100k_base encoding for all embedding models
        self._encoding = tiktoken.get_encoding("cl100k_base")

    async def close(self) -> None:
        """Close the underlying async OpenAI client."""
        await self._client.close()

    async def generate_embeddings(
        self,
        texts: list[str],
        model: str | None = None,
    ) -> list[EmbeddingResult]:
        """
        Generate embeddings for a batch of texts with retry logic.

        Args:
            texts: List of texts to embed
            model: Embedding model to use (optional, uses default)

        Returns:
            List of EmbeddingResult with vectors and metadata

        Raises:
            EmbeddingError: If embedding generation fails
            RateLimitError: If rate limit is exceeded after retries
        """
        model = model or self._settings.default_model

        if not self.is_model_supported(model):
            raise EmbeddingError(
                message=f"Unsupported embedding model: {model}",
                model=model,
                details={"supported_models": self.get_supported_models()},
            )

        retries = 0
        delay = self._settings.retry_delay_base

        while retries <= self._settings.max_retries:
            try:
                response = await self._client.embeddings.create(
                    input=texts,
                    model=self._settings.deployment_name,
                )

                dimension = self.get_model_dimension(model)
                results = []

                for i, embedding_data in enumerate(response.data):
                    token_count = self.count_tokens(texts[i], model)
                    results.append(
                        EmbeddingResult(
                            text=texts[i],
                            vector=embedding_data.embedding,
                            token_count=token_count,
                            model=model,
                            dimension=dimension,
                        )
                    )

                logger.info(f"Generated {len(results)} embeddings using {model}")
                return results

            except OpenAIRateLimitError as e:
                retries += 1
                if retries > self._settings.max_retries:
                    raise RateLimitError(
                        message=f"Rate limit exceeded after {retries} retries",
                        retry_after_seconds=delay,
                    ) from e

                logger.warning(
                    f"Rate limit hit, retrying in {delay}s "
                    f"(attempt {retries}/{self._settings.max_retries})"
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, self._settings.retry_delay_max)

            except Exception as e:
                logger.error(f"Embedding generation failed: {str(e)}", exc_info=True)
                raise EmbeddingError(
                    message=f"Failed to generate embeddings: {str(e)}",
                    model=model,
                ) from e

        raise EmbeddingError(
            message="Failed to generate embeddings after retries",
            model=model,
        )

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
        Count tokens in text using tiktoken.

        Args:
            text: The text to count tokens for
            model: The model (unused, all models use same encoding)

        Returns:
            The number of tokens in the text
        """
        return len(self._encoding.encode(text))
