"""Unit tests for BlobStoreAdapter."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config.settings import AzureStorageSettings
from src.infrastructure.azure.adapters.blob_store_adapter import BlobStoreAdapter


@pytest.fixture
def blob_store_adapter(
    mock_blob_client: MagicMock,
    azure_storage_settings: AzureStorageSettings,
) -> BlobStoreAdapter:
    """Create adapter with mocked underlying blob client."""
    return BlobStoreAdapter(
        blob_client=mock_blob_client,
        settings=azure_storage_settings,
    )


@pytest.mark.unit
class TestBlobStoreAdapter:
    """Tests for low-level blob methods exposed by the adapter."""

    async def test_upload_blob_delegates_to_client(
        self,
        blob_store_adapter: BlobStoreAdapter,
        mock_blob_client: MagicMock,
    ) -> None:
        expected = {"etag": "etag-1", "container": "chunks", "blob_path": "a/b.json"}
        mock_blob_client.upload_blob = AsyncMock(return_value=expected)

        result = await blob_store_adapter.upload_blob(
            container="chunks",
            blob_path="a/b.json",
            data='{"x":1}',
            content_type="application/json",
            overwrite=False,
            metadata={"tenant_id": "t1"},
        )

        assert result == expected
        mock_blob_client.upload_blob.assert_awaited_once_with(
            container="chunks",
            blob_path="a/b.json",
            data='{"x":1}',
            content_type="application/json",
            overwrite=False,
            metadata={"tenant_id": "t1"},
        )

    async def test_blob_exists_delegates_to_client(
        self,
        blob_store_adapter: BlobStoreAdapter,
        mock_blob_client: MagicMock,
    ) -> None:
        mock_blob_client.blob_exists = AsyncMock(return_value=True)

        exists = await blob_store_adapter.blob_exists(
            container="text",
            blob_path="tenant/file/text.json",
        )

        assert exists is True
        mock_blob_client.blob_exists.assert_awaited_once_with(
            "text",
            "tenant/file/text.json",
        )

    async def test_download_blob_delegates_to_client(
        self,
        blob_store_adapter: BlobStoreAdapter,
        mock_blob_client: MagicMock,
    ) -> None:
        payload = b"chunk content"
        mock_blob_client.download_blob = AsyncMock(return_value=payload)

        result = await blob_store_adapter.download_blob(
            container="chunks",
            blob_path="tenant/file/chunks/ch-1.json",
        )

        assert result == payload
        mock_blob_client.download_blob.assert_awaited_once_with(
            "chunks",
            "tenant/file/chunks/ch-1.json",
        )

    async def test_list_blobs_delegates_to_client(
        self,
        blob_store_adapter: BlobStoreAdapter,
        mock_blob_client: MagicMock,
    ) -> None:
        expected = [
            {"name": "tenant/file/embeddings/1.json", "size": 123},
            {"name": "tenant/file/embeddings/2.json", "size": 456},
        ]
        mock_blob_client.list_blobs = AsyncMock(return_value=expected)

        result = await blob_store_adapter.list_blobs(
            container="embeddings",
            prefix="tenant/file/embeddings/",
            max_results=100,
        )

        assert result == expected
        mock_blob_client.list_blobs.assert_awaited_once_with(
            container="embeddings",
            prefix="tenant/file/embeddings/",
            max_results=100,
        )
