"""Azure service adapters implementing application ports."""

from src.infrastructure.azure.adapters.blob_store_adapter import BlobStoreAdapter
from src.infrastructure.azure.adapters.document_intelligence_azure import (
    AzureDocumentIntelligenceAdapter,
)
from src.infrastructure.azure.adapters.document_intelligence_fake import (
    FakeDocumentIntelligenceAdapter,
)
from src.infrastructure.azure.adapters.embedding_azure_openai import AzureOpenAIEmbeddings
from src.infrastructure.azure.adapters.embedding_fake import FakeEmbeddings
from src.infrastructure.azure.adapters.vector_search_azure import AzureAISearchAdapter

__all__ = [
    "BlobStoreAdapter",
    "FakeDocumentIntelligenceAdapter",
    "AzureDocumentIntelligenceAdapter",
    "AzureOpenAIEmbeddings",
    "FakeEmbeddings",
    "AzureAISearchAdapter",
]
