"""Upload document and enqueue processing use case."""

import logging
from typing import Any

from src.application.dto.document_dto import UploadDocumentInput, UploadDocumentOutput
from src.application.ports.queue_publisher import QueuePublisherPort
from src.application.use_cases.upload_document import UploadDocumentUseCase

logger = logging.getLogger(__name__)


class UploadAndEnqueueDocumentUseCase:
    """
    Orchestrates document upload and processing queue publication.

    Keeps HTTP routes thin by encapsulating the workflow here.
    """

    def __init__(
        self,
        upload_use_case: UploadDocumentUseCase,
        queue_publisher: QueuePublisherPort,
        queue_name: str,
    ) -> None:
        """
        Initialize the use case.

        Args:
            upload_use_case: UploadDocumentUseCase for blob+metadata persistence
            queue_publisher: Queue publisher port implementation
            queue_name: Target processing queue name
        """
        self._upload_use_case = upload_use_case
        self._queue_publisher = queue_publisher
        self._queue_name = queue_name

    async def execute(self, input_dto: UploadDocumentInput) -> UploadDocumentOutput:
        """
        Execute upload, then enqueue processing message.

        Upload succeeds even if enqueue fails; enqueue errors are logged.
        """
        output = await self._upload_use_case.execute(input_dto)

        payload: dict[str, Any] = {
            "filename": output.filename,
            "chunking_strategy": input_dto.chunking_strategy.model_dump(mode="json"),
        }

        try:
            await self._queue_publisher.publish(
                queue_name=self._queue_name,
                tenant_id=input_dto.tenant_id,
                file_id=output.file_id,
                file_version=1,
                payload=payload,
            )
            logger.info(
                "Published to processing queue: file_id=%s, queue=%s",
                output.file_id,
                self._queue_name,
            )
        except Exception as e:
            logger.error(
                "Failed to publish to queue: file_id=%s, queue=%s, error=%s",
                output.file_id,
                self._queue_name,
                e,
            )

        return output
