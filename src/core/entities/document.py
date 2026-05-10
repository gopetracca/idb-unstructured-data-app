"""Document entity for file identity and storage references.

Maps 1:1 to the `files` SQL table. Holds stable document attributes
that rarely change after upload.
"""

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class Document(BaseModel):
    """Document identity and storage — maps to `files` table.

    Represents a document's stable attributes: identity, file properties,
    blob storage references, flexible metadata, and external identifiers.
    """

    # Identity (required)
    tenant_id: str = Field(..., description="Tenant identifier (PartitionKey)")
    file_id: str = Field(..., description="Unique file identifier (RowKey)")

    # File attributes
    blob_name: str = Field(..., description="Original filename")
    content_type: str = Field(
        default="application/octet-stream", description="MIME type"
    )
    size_bytes: int = Field(default=0, ge=0, description="File size in bytes")
    content_hash: str = Field(default="", description="SHA-256 hash of content")
    file_version: int = Field(default=1, ge=1, description="Version number")
    upload_timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Upload time"
    )
    last_updated: datetime = Field(
        default_factory=datetime.utcnow, description="Last modification time"
    )

    # Blob storage references (SSOT for content location)
    raw_blob_ref: str | None = Field(
        default=None,
        description="Blob storage path for raw uploaded file",
    )
    text_blob_ref: str | None = Field(
        default=None,
        description="Blob storage path for extracted text",
    )

    # External identifiers
    collection_name: str | None = Field(
        default=None,
        description="Collection to which the document will be ingested",
    )
    ezshare_id: str | None = Field(
        default=None,
        max_length=100,
        description="External document management system ID",
    )
