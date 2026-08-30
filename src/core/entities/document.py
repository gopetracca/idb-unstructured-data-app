"""Document entity for file identity and storage references.

Maps 1:1 to the `files` SQL table. Holds stable document attributes
that rarely change after upload.
"""

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ReplacedBlobReferences(BaseModel):
    """The blob references a reference update overwrote.

    Returned by the update rather than read beforehand: between reading and writing,
    another extraction of the same document can publish, and a run that swept what it saw
    at the start would delete that run's outputs while leaking its own. Only the update
    itself knows what it actually displaced.
    """

    text_blob_ref: str | None = Field(default=None)
    analysis_blob_ref: str | None = Field(default=None)


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
    analysis_blob_ref: str | None = Field(
        default=None,
        description=(
            "Blob storage path for the verbatim extraction-service response. The path is "
            "unique per extraction run, so this column is the only way to locate it. "
            "Null means the raw analysis was not captured — either the document was "
            "extracted before it was preserved, or persistence was disabled."
        ),
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
