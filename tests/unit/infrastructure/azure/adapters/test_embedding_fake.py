"""Unit tests for FakeEmbeddings adapter."""

import pytest

from src.core.errors import EmbeddingError
from src.infrastructure.azure.adapters.embedding_fake import FakeEmbeddings


@pytest.fixture
def fake_embeddings() -> FakeEmbeddings:
    """Create a FakeEmbeddings instance for testing."""
    return FakeEmbeddings(simulated_delay_seconds=0.0)


class TestFakeEmbeddings:
    """Tests for FakeEmbeddings adapter."""

    async def test_generate_embeddings_basic(self, fake_embeddings: FakeEmbeddings):
        """Test basic embedding generation."""
        texts = ["Hello world", "Test text"]

        results = await fake_embeddings.generate_embeddings(texts)

        assert len(results) == 2
        assert all(r.dimension == 1536 for r in results)
        assert all(len(r.vector) == 1536 for r in results)
        assert all(r.model == "text-embedding-3-small" for r in results)

    async def test_generate_embeddings_single_text(self, fake_embeddings: FakeEmbeddings):
        """Test embedding generation for a single text."""
        texts = ["Single text"]

        results = await fake_embeddings.generate_embeddings(texts)

        assert len(results) == 1
        assert results[0].text == "Single text"
        assert len(results[0].vector) == 1536

    async def test_generate_embeddings_empty_list(self, fake_embeddings: FakeEmbeddings):
        """Test embedding generation with empty input."""
        texts = []

        results = await fake_embeddings.generate_embeddings(texts)

        assert len(results) == 0

    async def test_generate_embeddings_deterministic(self, fake_embeddings: FakeEmbeddings):
        """Test that same text produces same embedding."""
        text = "Consistent text"

        results1 = await fake_embeddings.generate_embeddings([text])
        results2 = await fake_embeddings.generate_embeddings([text])

        assert results1[0].vector == results2[0].vector

    async def test_generate_embeddings_different_texts(self, fake_embeddings: FakeEmbeddings):
        """Test that different texts produce different embeddings."""
        texts = ["First text", "Second text"]

        results = await fake_embeddings.generate_embeddings(texts)

        assert results[0].vector != results[1].vector

    async def test_generate_embeddings_custom_model(self, fake_embeddings: FakeEmbeddings):
        """Test embedding generation with custom model."""
        texts = ["Test text"]

        results = await fake_embeddings.generate_embeddings(
            texts, model="text-embedding-3-large"
        )

        assert len(results) == 1
        assert results[0].model == "text-embedding-3-large"
        assert results[0].dimension == 3072
        assert len(results[0].vector) == 3072

    async def test_generate_embeddings_unsupported_model(self, fake_embeddings: FakeEmbeddings):
        """Test embedding generation with unsupported model raises error."""
        texts = ["Test text"]

        with pytest.raises(EmbeddingError) as exc_info:
            await fake_embeddings.generate_embeddings(texts, model="unsupported-model")

        assert "Unsupported embedding model" in str(exc_info.value)

    async def test_generate_embeddings_token_count(self, fake_embeddings: FakeEmbeddings):
        """Test that token count is estimated."""
        texts = ["Hello world"]  # ~3 tokens with 4 char/token estimate

        results = await fake_embeddings.generate_embeddings(texts)

        assert results[0].token_count > 0

    async def test_generate_embeddings_normalized_vectors(self, fake_embeddings: FakeEmbeddings):
        """Test that generated vectors are normalized."""
        texts = ["Test text"]

        results = await fake_embeddings.generate_embeddings(texts)

        # Check that vector is approximately unit length
        vector = results[0].vector
        magnitude = sum(v * v for v in vector) ** 0.5
        assert abs(magnitude - 1.0) < 0.001

    def test_get_supported_models(self, fake_embeddings: FakeEmbeddings):
        """Test getting supported models."""
        models = fake_embeddings.get_supported_models()

        assert "text-embedding-3-small" in models
        assert "text-embedding-3-large" in models

    def test_is_model_supported(self, fake_embeddings: FakeEmbeddings):
        """Test checking model support."""
        assert fake_embeddings.is_model_supported("text-embedding-3-small") is True
        assert fake_embeddings.is_model_supported("text-embedding-3-large") is True
        assert fake_embeddings.is_model_supported("unknown-model") is False

    def test_get_model_dimension(self, fake_embeddings: FakeEmbeddings):
        """Test getting model dimensions."""
        assert fake_embeddings.get_model_dimension("text-embedding-3-small") == 1536
        assert fake_embeddings.get_model_dimension("text-embedding-3-large") == 3072

    def test_get_model_dimension_unknown(self, fake_embeddings: FakeEmbeddings):
        """Test getting dimension for unknown model raises error."""
        with pytest.raises(EmbeddingError) as exc_info:
            fake_embeddings.get_model_dimension("unknown-model")

        assert "Unknown model" in str(exc_info.value)

    def test_count_tokens(self, fake_embeddings: FakeEmbeddings):
        """Test token counting."""
        # With 4 chars per token approximation
        assert fake_embeddings.count_tokens("test") >= 1
        assert fake_embeddings.count_tokens("a" * 100) == 25

    def test_count_tokens_empty(self, fake_embeddings: FakeEmbeddings):
        """Test token counting with empty string."""
        assert fake_embeddings.count_tokens("") == 1  # min of 1

    async def test_simulated_delay(self):
        """Test that simulated delay works."""
        import time

        embeddings = FakeEmbeddings(simulated_delay_seconds=0.1)

        start = time.time()
        await embeddings.generate_embeddings(["Test"])
        elapsed = time.time() - start

        assert elapsed >= 0.1

    def test_default_model(self):
        """Test default model configuration."""
        embeddings = FakeEmbeddings(default_model="text-embedding-3-large")

        assert embeddings._default_model == "text-embedding-3-large"

    async def test_generate_embeddings_uses_default_model(self):
        """Test that default model is used when not specified."""
        embeddings = FakeEmbeddings(
            simulated_delay_seconds=0.0, default_model="text-embedding-3-large"
        )

        results = await embeddings.generate_embeddings(["Test"])

        assert results[0].model == "text-embedding-3-large"
        assert results[0].dimension == 3072
