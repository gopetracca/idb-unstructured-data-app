"""Document analysis entities and value objects for Document Intelligence processing."""

from datetime import datetime

from pydantic import BaseModel, Field


class PageContent(BaseModel):
    """Value object representing content extracted from a single page."""

    page_number: int = Field(..., ge=1, description="Page number (1-indexed)")
    text: str = Field(default="", description="Extracted text content")
    word_count: int = Field(default=0, ge=0, description="Number of words on the page")


class ExtractionMetadata(BaseModel):
    """Value object for document extraction metadata."""

    page_count: int = Field(default=0, ge=0, description="Total number of pages")
    word_count: int = Field(default=0, ge=0, description="Total word count")
    extraction_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Extraction confidence score"
    )
    extraction_method: str = Field(
        default="azure-document-intelligence",
        description="Method used for extraction",
    )
    api_version: str = Field(default="2024-11-30", description="API version used")


class MarkdownOutput(BaseModel):
    """
    Value object representing document analysis output.

    This is the primary output stored in the text container.
    """

    file_id: str = Field(..., description="Unique file identifier")
    file_version: int = Field(default=1, ge=1, description="File version number")
    extracted_text: str = Field(default="", description="Full extracted text content")
    pages: list[PageContent] = Field(default_factory=list, description="Per-page content")
    extraction_metadata: ExtractionMetadata = Field(
        default_factory=ExtractionMetadata,
        description="Extraction metadata",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when extraction was performed",
    )



class DocumentMetadata(BaseModel):
    """Metadata about a document to be processed."""

    file_id: str = Field(..., description="Unique file identifier")
    file_version: int = Field(default=1, ge=1, description="File version number")
    blob_name: str = Field(..., description="Original blob/file name")
    content_type: str = Field(
        default="application/octet-stream",
        description="MIME type of the document",
    )
    size_bytes: int = Field(default=0, ge=0, description="File size in bytes")
    source_container: str = Field(default="raw", description="Source blob container")
    source_path: str = Field(default="", description="Full path in source container")
