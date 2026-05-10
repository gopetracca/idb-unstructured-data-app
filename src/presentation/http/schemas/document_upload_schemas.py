"""Typed form schemas for type-specific document upload endpoints.

These schemas provide strong typing for operational and publication document
uploads, ensuring that document-type-specific fields are validated at the API layer.
"""

from datetime import datetime
from typing import Annotated

from fastapi import Form
from pydantic import BaseModel, Field


class OperationalDocumentUploadForm(BaseModel):
    """Form schema for operational document uploads.

    Contains fields specific to operational documents (loans, grants, TCs)
    in addition to common document fields.
    """

    # Required fields
    collection_name: str = Field(..., description="Collection to ingest the document into")
    ezshare_id: str = Field(
        ...,
        description="External document ID (e.g., EZSHARE-510177122-450). Must be unique per tenant.",
    )

    # Common optional fields
    language: str | None = Field(default="en", description="ISO 639-1 language code")
    country: str | None = Field(default=None, description="Country")
    year: int | None = Field(default=None, description="Publication year", ge=1900, le=2100)
    document_author: str | None = Field(default=None, description="Document author")
    document_name: str | None = Field(default=None, description="Document display name")
    document_url: str | None = Field(default=None, description="URL of the document")
    disclosed: bool | None = Field(default=None, description="Disclosure status")
    access_to_information_policy: str | None = Field(default=None, description="Access policy")
    document_publish_date: datetime | None = Field(default=None, description="Publication date")
    document_approval_date: datetime | None = Field(default=None, description="Approval date")
    document_created_date: datetime | None = Field(default=None, description="Created date")
    source: str | None = Field(default=None, description="Source system")
    department: str | None = Field(default=None, description="Department")
    description: str | None = Field(default=None, description="Document description")
    tags: str | None = Field(default=None, description="Comma-separated tags")

    # Operational-specific fields
    operation_number: str | None = Field(
        default=None, description="Operation number (e.g., UR-P1180)"
    )
    sector: str | None = Field(default=None, description="Sector classification (e.g., TRANSPORT)")
    operation_type: str | None = Field(default=None, description="Operation type (e.g., Loan)")
    dept_id: str | None = Field(default=None, description="Department ID (e.g., INE/TSP)")

    model_config = {"extra": "forbid"}

    @classmethod
    def as_form(
        cls,
        collection_name: Annotated[
            str,
            Form(description="Collection to ingest the document into"),
        ],
        ezshare_id: Annotated[
            str,
            Form(
                description="External document ID (e.g., EZSHARE-510177122-450). Must be unique per tenant.",
                examples=["EZSHARE-510177122-450"],
            ),
        ],
        # Common optional fields
        language: Annotated[
            str | None,
            Form(description="ISO 639-1 language code"),
        ] = "en",
        country: Annotated[
            str | None,
            Form(description="Country"),
        ] = None,
        year: Annotated[
            int | None,
            Form(description="Publication year"),
        ] = None,
        document_author: Annotated[
            str | None,
            Form(description="Document author"),
        ] = None,
        document_name: Annotated[
            str | None,
            Form(description="Document display name"),
        ] = None,
        document_url: Annotated[
            str | None,
            Form(description="URL of the document"),
        ] = None,
        disclosed: Annotated[
            bool | None,
            Form(description="Disclosure status"),
        ] = None,
        access_to_information_policy: Annotated[
            str | None,
            Form(description="Access to information policy"),
        ] = None,
        document_publish_date: Annotated[
            datetime | None,
            Form(description="Publication date (ISO 8601)"),
        ] = None,
        document_approval_date: Annotated[
            datetime | None,
            Form(description="Approval date (ISO 8601)"),
        ] = None,
        document_created_date: Annotated[
            datetime | None,
            Form(description="Created date (ISO 8601)"),
        ] = None,
        source: Annotated[
            str | None,
            Form(description="Source system"),
        ] = None,
        department: Annotated[
            str | None,
            Form(description="Department"),
        ] = None,
        description: Annotated[
            str | None,
            Form(description="Document description"),
        ] = None,
        tags: Annotated[
            str | None,
            Form(description="Comma-separated tags"),
        ] = None,
        # Operational-specific fields
        operation_number: Annotated[
            str | None,
            Form(description="Operation number (e.g., UR-P1180)"),
        ] = None,
        sector: Annotated[
            str | None,
            Form(description="Sector classification (e.g., TRANSPORT)"),
        ] = None,
        operation_type: Annotated[
            str | None,
            Form(description="Operation type (e.g., Loan)"),
        ] = None,
        dept_id: Annotated[
            str | None,
            Form(description="Department ID (e.g., INE/TSP)"),
        ] = None,
    ) -> "OperationalDocumentUploadForm":
        """Build the form model from multipart/form-data fields."""
        return cls(
            collection_name=collection_name,
            ezshare_id=ezshare_id,
            language=language,
            country=country,
            year=year,
            document_author=document_author,
            document_name=document_name,
            document_url=document_url,
            disclosed=disclosed,
            access_to_information_policy=access_to_information_policy,
            document_publish_date=document_publish_date,
            document_approval_date=document_approval_date,
            document_created_date=document_created_date,
            source=source,
            department=department,
            description=description,
            tags=tags,
            operation_number=operation_number,
            sector=sector,
            operation_type=operation_type,
            dept_id=dept_id,
        )

    def to_metadata_dict(self) -> dict:
        """Convert form data to metadata dictionary for use case input.

        Sets document_type to 'operational' and parses tags from comma-separated string.
        """
        data = self.model_dump(exclude={"collection_name", "ezshare_id"}, exclude_none=True)
        data["document_type"] = "operational"

        # Parse tags from comma-separated string
        if "tags" in data and isinstance(data["tags"], str):
            data["tags"] = [t.strip() for t in data["tags"].split(",") if t.strip()]

        return data


class PublicationDocumentUploadForm(BaseModel):
    """Form schema for publication document uploads.

    Contains fields specific to research publications (journals, working papers, etc.)
    in addition to common document fields.
    """

    # Required fields
    collection_name: str = Field(..., description="Collection to ingest the document into")
    ezshare_id: str = Field(
        ...,
        description="External document ID (e.g., EZSHARE-510177122-450). Must be unique per tenant.",
    )

    # Common optional fields
    language: str | None = Field(default="en", description="ISO 639-1 language code")
    country: str | None = Field(default=None, description="Country")
    year: int | None = Field(default=None, description="Publication year", ge=1900, le=2100)
    document_author: str | None = Field(default=None, description="Document author")
    document_name: str | None = Field(default=None, description="Document display name")
    document_url: str | None = Field(default=None, description="URL of the document")
    disclosed: bool | None = Field(default=None, description="Disclosure status")
    access_to_information_policy: str | None = Field(default=None, description="Access policy")
    document_publish_date: datetime | None = Field(default=None, description="Publication date")
    document_approval_date: datetime | None = Field(default=None, description="Approval date")
    document_created_date: datetime | None = Field(default=None, description="Created date")
    source: str | None = Field(default=None, description="Source system")
    department: str | None = Field(default=None, description="Department")
    description: str | None = Field(default=None, description="Document description")
    tags: str | None = Field(default=None, description="Comma-separated tags")

    # Publication-specific fields
    journal: str | None = Field(
        default=None, description="Journal or publication venue name"
    )
    doi: str | None = Field(default=None, description="Digital Object Identifier")
    issn: str | None = Field(default=None, description="International Standard Serial Number")
    peer_reviewed: bool | None = Field(
        default=None, description="Whether the publication was peer-reviewed"
    )
    publication_type: str | None = Field(
        default=None,
        description="Type of publication (journal_article, working_paper, book_chapter)",
    )
    publication_date: datetime | None = Field(default=None, description="Date of publication")

    model_config = {"extra": "forbid"}

    @classmethod
    def as_form(
        cls,
        collection_name: Annotated[
            str,
            Form(description="Collection to ingest the document into"),
        ],
        ezshare_id: Annotated[
            str,
            Form(
                description="External document ID (e.g., EZSHARE-510177122-450). Must be unique per tenant.",
                examples=["EZSHARE-510177122-450"],
            ),
        ],
        # Common optional fields
        language: Annotated[
            str | None,
            Form(description="ISO 639-1 language code"),
        ] = "en",
        country: Annotated[
            str | None,
            Form(description="Country"),
        ] = None,
        year: Annotated[
            int | None,
            Form(description="Publication year"),
        ] = None,
        document_author: Annotated[
            str | None,
            Form(description="Document author"),
        ] = None,
        document_name: Annotated[
            str | None,
            Form(description="Document display name"),
        ] = None,
        document_url: Annotated[
            str | None,
            Form(description="URL of the document"),
        ] = None,
        disclosed: Annotated[
            bool | None,
            Form(description="Disclosure status"),
        ] = None,
        access_to_information_policy: Annotated[
            str | None,
            Form(description="Access to information policy"),
        ] = None,
        document_publish_date: Annotated[
            datetime | None,
            Form(description="Publication date (ISO 8601)"),
        ] = None,
        document_approval_date: Annotated[
            datetime | None,
            Form(description="Approval date (ISO 8601)"),
        ] = None,
        document_created_date: Annotated[
            datetime | None,
            Form(description="Created date (ISO 8601)"),
        ] = None,
        source: Annotated[
            str | None,
            Form(description="Source system"),
        ] = None,
        department: Annotated[
            str | None,
            Form(description="Department"),
        ] = None,
        description: Annotated[
            str | None,
            Form(description="Document description"),
        ] = None,
        tags: Annotated[
            str | None,
            Form(description="Comma-separated tags"),
        ] = None,
        # Publication-specific fields
        journal: Annotated[
            str | None,
            Form(description="Journal or publication venue name"),
        ] = None,
        doi: Annotated[
            str | None,
            Form(description="Digital Object Identifier (e.g., 10.1234/example.2024.001)"),
        ] = None,
        issn: Annotated[
            str | None,
            Form(description="International Standard Serial Number"),
        ] = None,
        peer_reviewed: Annotated[
            bool | None,
            Form(description="Whether the publication was peer-reviewed"),
        ] = None,
        publication_type: Annotated[
            str | None,
            Form(description="Type of publication (journal_article, working_paper, book_chapter)"),
        ] = None,
        publication_date: Annotated[
            datetime | None,
            Form(description="Date of publication (ISO 8601)"),
        ] = None,
    ) -> "PublicationDocumentUploadForm":
        """Build the form model from multipart/form-data fields."""
        return cls(
            collection_name=collection_name,
            ezshare_id=ezshare_id,
            language=language,
            country=country,
            year=year,
            document_author=document_author,
            document_name=document_name,
            document_url=document_url,
            disclosed=disclosed,
            access_to_information_policy=access_to_information_policy,
            document_publish_date=document_publish_date,
            document_approval_date=document_approval_date,
            document_created_date=document_created_date,
            source=source,
            department=department,
            description=description,
            tags=tags,
            journal=journal,
            doi=doi,
            issn=issn,
            peer_reviewed=peer_reviewed,
            publication_type=publication_type,
            publication_date=publication_date,
        )

    def to_metadata_dict(self) -> dict:
        """Convert form data to metadata dictionary for use case input.

        Sets document_type to 'publication' and parses tags from comma-separated string.
        """
        data = self.model_dump(exclude={"collection_name", "ezshare_id"}, exclude_none=True)
        data["document_type"] = "publication"

        # Parse tags from comma-separated string
        if "tags" in data and isinstance(data["tags"], str):
            data["tags"] = [t.strip() for t in data["tags"].split(",") if t.strip()]

        return data
