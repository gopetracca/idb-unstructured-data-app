"""Azure AI Search client wrapper for managing search connections."""

import logging

from azure.core.credentials import AzureKeyCredential, TokenCredential
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient

from src.infrastructure.azure.clients.credentials import AzureCredential, get_azure_credential

logger = logging.getLogger(__name__)


class SearchClientWrapper:
    """
    Manages Azure AI Search client instances with connection pooling.

    This wrapper provides centralized management of SearchClient and
    SearchIndexClient instances, with pooling to reuse connections per index.

    Supports both key-based auth (AzureKeyCredential) and managed identity
    (DefaultAzureCredential) depending on whether api_key is provided.

    Example (key-based):
        >>> async with SearchClientWrapper(endpoint, api_key="...") as wrapper:
        ...     search_client = wrapper.get_search_client("my-index")

    Example (managed identity):
        >>> async with SearchClientWrapper(endpoint) as wrapper:
        ...     search_client = wrapper.get_search_client("my-index")
    """

    def __init__(self, endpoint: str, api_key: str = "", managed_identity_client_id: str = ""):
        """
        Initialize the search client wrapper.

        Args:
            endpoint: Azure AI Search endpoint URL
            api_key: Azure AI Search API key. If empty, DefaultAzureCredential is used.
            managed_identity_client_id: Client ID of a user-assigned managed identity.
        """
        self.endpoint = endpoint
        self.credential: AzureCredential = get_azure_credential(api_key, managed_identity_client_id or None)
        self.index_client = SearchIndexClient(
            endpoint=self.endpoint, credential=self.credential
        )
        self._search_clients: dict[str, SearchClient] = {}

        logger.debug("Initialized SearchClientWrapper for endpoint: %s", endpoint)

    def get_search_client(self, index_name: str) -> SearchClient:
        """
        Get or create a SearchClient for a specific index.

        This method implements client pooling - reusing existing clients
        when possible to reduce connection overhead.

        Args:
            index_name: Name of the search index

        Returns:
            SearchClient instance for the specified index
        """
        if index_name not in self._search_clients:
            self._search_clients[index_name] = SearchClient(
                endpoint=self.endpoint,
                index_name=index_name,  # IMPORTANT: Use 'index_name', not 'collection_name'
                credential=self.credential,
            )
            logger.debug("Created new SearchClient for index: %s", index_name)

        return self._search_clients[index_name]

    async def close(self) -> None:
        """
        Close all search clients and release resources.

        This should be called when the wrapper is no longer needed,
        typically in an async context manager's __aexit__ method.
        """
        logger.debug("Closing all search clients...")

        # Close index client
        await self.index_client.close()

        # Close all search clients
        for index_name, client in self._search_clients.items():
            await client.close()
            logger.debug("Closed SearchClient for index: %s", index_name)

        self._search_clients.clear()

        logger.debug("All search clients closed")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - ensures clients are closed."""
        await self.close()
        return False  # Don't suppress exceptions

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"SearchClientWrapper(endpoint={self.endpoint}, "
            f"active_clients={len(self._search_clients)})"
        )
