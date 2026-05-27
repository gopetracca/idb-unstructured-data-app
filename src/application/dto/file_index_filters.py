"""Type-safe filter options for FileIndex queries."""

from pydantic import BaseModel


class FileIndexFilters(BaseModel):
    """
    Type-safe filter options for FileIndex queries.

    All fields are optional. Only non-None values are applied by the repository.

    Supported filters:
    - operation_number: Exact match on operation number (e.g., "UR-P1180")
    - sector: Exact match on sector (e.g., "TRANSPORT")
    - country: Exact match on country
    - operation_type: Exact match on operation type
    - dept_id: Exact match on department ID (e.g., "EXR/CMG")
    - disclosed: Boolean filter for disclosure status
    - year: Integer filter for publication year
    - document_author: Exact match on document author
    - file_extension: Exact match on file extension (normalized with dot)
    - ezshare_id: Exact match on EZSHARE ID
    - document_name: Exact match on document name

    Note: Full-text capabilities depend on the active metadata-store implementation.
    """

    document_category: str | None = None
    document_type: str | None = None
    language: str | None = None
    operation_number: str | None = None
    sector: str | None = None
    country: str | None = None
    operation_type: str | None = None
    dept_id: str | None = None
    disclosed: bool | None = None
    year: int | None = None
    document_author: str | None = None
    file_extension: str | None = None
    ezshare_id: str | None = None
    document_name: str | None = None

    model_config = {"extra": "forbid"}
