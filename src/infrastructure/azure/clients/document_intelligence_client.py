"""Azure Document Intelligence client wrapper."""

import asyncio
import io
import logging
from typing import Any

from azure.ai.documentintelligence import DocumentIntelligenceClient as AzureDocIntelClient
from azure.ai.documentintelligence.models import (
    AnalyzeDocumentRequest,
    AnalyzeResult,
    DocumentContentFormat,
)
from azure.core.exceptions import HttpResponseError

from src.config.settings import DocumentIntelligenceSettings, get_settings
from src.infrastructure.azure.clients.credentials import get_azure_credential

logger = logging.getLogger(__name__)


class DocumentIntelligenceClient:
    """
    Client wrapper for Azure Document Intelligence service.

    Provides a simplified interface for document analysis operations
    with lazy initialization and proper resource management.
    """

    LAYOUT_MODEL = "prebuilt-layout"

    def __init__(self, settings: DocumentIntelligenceSettings | None = None) -> None:
        self._settings = settings or get_settings().document_intelligence
        self._client: AzureDocIntelClient | None = None

    @property
    def endpoint(self) -> str:
        return self._settings.endpoint

    @property
    def api_version(self) -> str:
        return self._settings.api_version

    def _get_client(self) -> AzureDocIntelClient:
        if self._client is None:
            if not self._settings.endpoint:
                raise ValueError(
                    "Document Intelligence endpoint must be configured. "
                    "Set DOCUMENT_INTELLIGENCE_ENDPOINT environment variable."
                )
            self._client = AzureDocIntelClient(
                endpoint=self._settings.endpoint,
                credential=get_azure_credential(
                    self._settings.api_key, get_settings().azure_client_id or None
                ),
                api_version=self._settings.api_version,
            )
            logger.info(
                "Document Intelligence client initialized for endpoint: %s",
                self._settings.endpoint,
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
            logger.info("Document Intelligence client closed")

    async def analyze_document(
        self,
        document_content: bytes,
        content_type: str,
        output_format: DocumentContentFormat = DocumentContentFormat.MARKDOWN,
    ) -> AnalyzeResult:
        """
        Analyze a document and extract content.

        The underlying SDK is synchronous; the blocking poller.result() call is
        offloaded to a thread via asyncio.to_thread so the event loop is not blocked.
        """
        client = self._get_client()

        logger.info(
            "Analyzing document: content_type=%s, size=%d bytes, output_format=%s",
            content_type,
            len(document_content),
            output_format,
        )

        def _run() -> AnalyzeResult:
            body = io.BytesIO(document_content)
            poller = client.begin_analyze_document(
                model_id=self.LAYOUT_MODEL,
                body=body,
                content_type=content_type,
                output_content_format=output_format,
            )
            return poller.result()

        try:
            result: AnalyzeResult = await asyncio.to_thread(_run)
        except HttpResponseError as e:
            logger.error(
                "Document Intelligence API error: status=%s, message=%s",
                e.status_code,
                e.message,
            )
            raise

        logger.info(
            "Document analysis completed: pages=%d",
            len(result.pages) if result.pages else 0,
        )
        return result

    @staticmethod
    def to_raw_payload(result: AnalyzeResult) -> dict[str, Any]:
        """Serialise an analysis result verbatim, including fields the SDK does not model.

        The generated SDK models are mapping-backed, so `as_dict()` round-trips whatever
        the service actually sent — including keys added by a newer service version that
        this SDK has no attribute for. That is the point: the raw copy must not be a
        filter, or it would lose exactly what filtering already lost once.
        """
        return result.as_dict()

    async def analyze_document_from_url(
        self,
        document_url: str,
        output_format: DocumentContentFormat = DocumentContentFormat.MARKDOWN,
    ) -> AnalyzeResult:
        """
        Analyze a document from a URL.

        The blocking poller.result() call is offloaded to a thread via asyncio.to_thread.
        """
        client = self._get_client()

        logger.info("Analyzing document from URL: %s...", document_url[:50])

        def _run() -> AnalyzeResult:
            poller = client.begin_analyze_document(
                model_id=self.LAYOUT_MODEL,
                body=AnalyzeDocumentRequest(url_source=document_url),
                output_content_format=output_format,
            )
            return poller.result()

        try:
            result: AnalyzeResult = await asyncio.to_thread(_run)
        except HttpResponseError as e:
            logger.error(
                "Document Intelligence API error: status=%s, message=%s",
                e.status_code,
                e.message,
            )
            raise

        logger.info(
            "Document analysis from URL completed: pages=%d",
            len(result.pages) if result.pages else 0,
        )
        return result

    def get_operation_result(self, operation_id: str) -> AnalyzeResult:
        raise NotImplementedError(
            "Getting operation result by ID is not yet implemented"
        )
