import io
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.config.settings import DocumentIntelligenceSettings
from src.infrastructure.azure.clients.document_intelligence_client import DocumentIntelligenceClient


async def test_analyze_document_uses_bytesio(monkeypatch):
    """Ensure raw bytes are sent as an IO body to the Azure SDK."""
    mock_client = MagicMock()
    poller = MagicMock()
    analyze_result = SimpleNamespace(pages=[])
    poller.result.return_value = analyze_result
    mock_client.begin_analyze_document.return_value = poller

    monkeypatch.setattr(
        "src.infrastructure.azure.clients.document_intelligence_client.AzureDocIntelClient",
        lambda *args, **kwargs: mock_client,
    )

    settings = DocumentIntelligenceSettings(endpoint="https://example", api_key="key")
    client = DocumentIntelligenceClient(settings=settings)

    data = b"hello world"
    result = await client.analyze_document(document_content=data, content_type="application/pdf")

    assert result is analyze_result

    assert mock_client.begin_analyze_document.called
    _, kwargs = mock_client.begin_analyze_document.call_args

    assert "body" in kwargs
    body = kwargs["body"]
    assert hasattr(body, "read")

    body.seek(0)
    assert body.read() == data

    assert kwargs.get("content_type") == "application/pdf"


@pytest.mark.parametrize(
    "endpoint,api_key",
    [
        ("", ""),
        ("", "key"),
    ],
)
async def test_analyze_document_requires_endpoint(endpoint, api_key):
    """Analyze should raise a ValueError if endpoint is not configured."""
    settings = DocumentIntelligenceSettings(endpoint=endpoint, api_key=api_key)
    client = DocumentIntelligenceClient(settings=settings)

    with pytest.raises(ValueError):
        await client.analyze_document(document_content=b"test", content_type="application/pdf")


def test_analyze_document_uses_managed_identity_when_no_api_key(monkeypatch):
    """When endpoint is set but api_key is empty, DefaultAzureCredential is used."""
    from azure.identity import DefaultAzureCredential
    from src.infrastructure.azure.clients.credentials import get_azure_credential

    credential = get_azure_credential("")
    assert isinstance(credential, DefaultAzureCredential)
