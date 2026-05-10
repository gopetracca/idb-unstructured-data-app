"""Azure Storage and AI clients for blob, queue, search, and document operations."""

from src.infrastructure.azure.clients.blob_client import BlobStorageClient
from src.infrastructure.azure.clients.credentials import get_azure_credential
from src.infrastructure.azure.clients.document_intelligence_client import (
    DocumentIntelligenceClient,
)
from src.infrastructure.azure.clients.queue_client import QueueStorageClient
from src.infrastructure.azure.clients.search_client import SearchClientWrapper

__all__ = [
    "BlobStorageClient",
    "QueueStorageClient",
    "DocumentIntelligenceClient",
    "SearchClientWrapper",
    "get_azure_credential",
]
