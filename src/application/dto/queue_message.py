"""DTOs for queue message handling."""

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class QueueMessageEnvelope(BaseModel):
    """
    Parsed queue message envelope.

    Matches the envelope structure created by QueueStorageClient._create_message_envelope()
    in src/infrastructure/azure/clients/queue_client.py
    """

    tenant_id: str = Field(..., alias="tenantId")
    file_id: str = Field(..., alias="fileId")
    file_version: int = Field(default=1, alias="fileVersion")
    operation_id: str = Field(..., alias="operationId")
    correlation_id: str = Field(..., alias="correlationId")
    timestamp: datetime
    retry_count: int = Field(default=0, alias="retryCount")
    payload: dict[str, Any] = Field(default_factory=dict)
    datadog_context: dict[str, str] = Field(
        default_factory=dict, alias="_datadog"
    )

    model_config = {"populate_by_name": True}

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v: str | datetime) -> datetime:
        """Parse ISO timestamp string to datetime."""
        if isinstance(v, str):
            return datetime.fromisoformat(v)
        return v

    @classmethod
    def from_queue_message(cls, raw_content: str) -> "QueueMessageEnvelope":
        """
        Parse raw queue message JSON into envelope.

        Args:
            raw_content: Raw JSON string from queue message body

        Returns:
            Parsed QueueMessageEnvelope

        Raises:
            ValueError: If message cannot be parsed
        """
        try:
            data = json.loads(raw_content)
            return cls(**data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in queue message: {e}") from e
        except Exception as e:
            raise ValueError(f"Invalid queue message envelope: {e}") from e
