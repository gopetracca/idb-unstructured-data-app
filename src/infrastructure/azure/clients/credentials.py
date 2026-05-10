"""Azure credential resolution supporting managed identity and key-based authentication."""

from azure.core.credentials import AzureKeyCredential, TokenCredential
from azure.identity import DefaultAzureCredential


def get_azure_credential(
    api_key: str | None, managed_identity_client_id: str | None = None
) -> AzureKeyCredential | DefaultAzureCredential:
    """
    Resolve the appropriate Azure credential based on configuration.

    Uses AzureKeyCredential when an API key is provided, falling back to
    DefaultAzureCredential for managed identity, workload identity, or
    developer credentials (az login / environment variables).

    Args:
        api_key: Optional API key. If non-empty, key-based auth is used.
        managed_identity_client_id: Client ID of a user-assigned managed identity.
            When set, pins DefaultAzureCredential to that specific identity instead
            of relying on system-assigned identity discovery.

    Returns:
        AzureKeyCredential if api_key is set, else DefaultAzureCredential.
    """
    if api_key:
        return AzureKeyCredential(api_key)
    if managed_identity_client_id:
        return DefaultAzureCredential(managed_identity_client_id=managed_identity_client_id)
    return DefaultAzureCredential()


# Type alias for annotating parameters that accept either credential type
AzureCredential = AzureKeyCredential | TokenCredential
