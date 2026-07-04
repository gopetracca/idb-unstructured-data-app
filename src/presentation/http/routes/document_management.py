"""Document management API routes (CRUD operations)."""

import json
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Security, UploadFile
from pydantic import ValidationError

from src.application.dto.document_dto import (
    DeleteDocumentInput,
    ListDocumentsInput,
    UpdateMetadataInput,
    UploadDocumentInput,
)
from src.application.use_cases.delete_document import DeleteDocumentUseCase
from src.application.use_cases.list_documents import ListDocumentsUseCase
from src.application.use_cases.update_metadata import UpdateMetadataUseCase
from src.application.use_cases.upload_and_enqueue_document import (
    UploadAndEnqueueDocumentUseCase,
)
from src.container import Container
from src.core.value_objects.document_metadata import METADATA_MODELS, get_metadata_model
from src.presentation.http.auth import CurrentUser, get_current_user
from src.presentation.http.schemas.chunking import UploadChunkingStrategyForm
from src.presentation.http.schemas.document_schemas import (
    DeleteDocumentResponse,
    DocumentSchema,
    ListDocumentsResponse,
    MetadataSchema,
    PaginationSchema,
    UpdateMetadataRequest,
    UpdateMetadataResponse,
    UploadDocumentResponse,
)
from src.presentation.http.tenant import TenantId

router = APIRouter(prefix="/api/v1/documents", tags=["document-management"])


_KNOWN_DOCUMENT_TYPES = list(METADATA_MODELS.keys())


@router.post(
    "",
    deprecated=True,
    response_model=UploadDocumentResponse,
    status_code=201,
    summary="Upload a document",
    description=f"""Upload a PDF or Word document with metadata for RAG processing.

**Document Types:** {", ".join(f"`{t}`" for t in _KNOWN_DOCUMENT_TYPES)}

The `metadata` JSON is validated against the schema for the specified `document_type`.
For a better developer experience with individual form fields, use the type-specific endpoints:
- `POST /api/v1/documents/operational`
- `POST /api/v1/documents/publication`
""",
)
@inject
async def upload_document(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=["api.write"])],
    file: Annotated[UploadFile, File(description="PDF or Word document to upload")],
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
    tenant_id: TenantId,
    document_type: Annotated[
        str,
        Form(
            description=f"Type of document being uploaded. One of: {', '.join(_KNOWN_DOCUMENT_TYPES)}",
            examples=["operational", "publication"],
        ),
    ] = "operational",
    metadata: Annotated[
        str | None,
        Form(
            description="Optional JSON string with document metadata (schema depends on document_type).",
        ),
    ] = None,
    chunking_strategy: UploadChunkingStrategyForm = Depends(
        UploadChunkingStrategyForm.as_form
    ),
    use_case: UploadAndEnqueueDocumentUseCase = Depends(
        Provide[Container.upload_and_enqueue_document_use_case]
    ),
) -> UploadDocumentResponse:
    """
    Upload a document to the RAG system.

    Accepts PDF and Word (.docx) files up to 50MB with optional metadata.
    Requires a unique ezshare_id for duplicate detection.
    Specify chunking via `chunking_strategy_name` + `chunking_parameters` JSON
    (defaults to fixed_size with chunk_size/chunk_overlap defaults).
    Returns the generated file ID and upload confirmation.
    """
    # Validate document_type
    if document_type not in METADATA_MODELS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "InvalidDocumentType",
                "message": f"Unknown document_type: '{document_type}'. Available: {', '.join(_KNOWN_DOCUMENT_TYPES)}",
            },
        )

    # Parse metadata JSON
    try:
        metadata_dict = json.loads(metadata) if metadata else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "InvalidMetadataJSON",
                "message": f"metadata is not valid JSON: {exc}",
            },
        )

    # Validate metadata against the document_type schema
    metadata_model_cls = get_metadata_model(document_type)
    try:
        validated = metadata_model_cls.model_validate({"file_id": "validation", **metadata_dict})
    except ValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "InvalidMetadata",
                "message": f"metadata does not match {document_type} schema",
                "details": exc.errors(),
            },
        )

    # Build final metadata dict from validated model, injecting document_category
    # The `document_type` form field on this (deprecated) generic endpoint acts as the
    # schema selector — its value IS the document_category (e.g. "operational", "publication").
    metadata_dict = validated.model_dump(exclude={"file_id"}, exclude_none=True)
    metadata_dict["document_category"] = document_type  # inject as discriminator field

    chunking_strategy_model = chunking_strategy.to_chunking_strategy()

    # Read file content
    content = await file.read()

    # Build input DTO
    input_dto = UploadDocumentInput(
        tenant_id=tenant_id,
        filename=file.filename or "unknown",
        content=content,
        content_type=file.content_type or "application/octet-stream",
        collection_name=collection_name,
        ezshare_id=ezshare_id,
        metadata=metadata_dict,
        chunking_strategy=chunking_strategy_model,
    )

    # Execute use case (upload + enqueue)
    output = await use_case.execute(input_dto)

    # Map to response
    return UploadDocumentResponse(
        file_id=output.file_id,
        filename=output.filename,
        size_bytes=output.size_bytes,
        mime_type=output.mime_type,
        uploaded_at=output.uploaded_at,
        metadata=MetadataSchema(**output.metadata.model_dump()),
    )


@router.patch(
    "/{id}",
    response_model=UpdateMetadataResponse,
    summary="Update document metadata",
    description="Update metadata for an existing document using PATCH semantics.",
)
@inject
async def update_document_metadata(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=["api.write"])],
    id: str,
    request: UpdateMetadataRequest,
    tenant_id: TenantId,
    use_case: UpdateMetadataUseCase = Depends(Provide[Container.update_metadata_use_case]),
) -> UpdateMetadataResponse:
    """
    Update metadata for an existing document.

    Supports partial updates - only provided fields are updated.
    Version number is automatically incremented.
    """
    # Build input DTO
    input_dto = UpdateMetadataInput(
        tenant_id=tenant_id,
        file_id=id,
        metadata_updates=request.to_update_dict(),
    )

    # Execute use case
    output = await use_case.execute(input_dto)

    # Map to response
    return UpdateMetadataResponse(
        file_id=output.file_id,
        filename=output.filename,
        updated_at=output.updated_at,
        metadata=MetadataSchema(**output.metadata.model_dump()),
    )


@router.delete(
    "/{id}",
    response_model=DeleteDocumentResponse,
    summary="Delete a document",
    description="Delete a document and its metadata from the system.",
)
@inject
async def delete_document(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=["api.write"])],
    id: str,
    tenant_id: TenantId,
    use_case: DeleteDocumentUseCase = Depends(Provide[Container.delete_document_use_case]),
) -> DeleteDocumentResponse:
    """
    Delete a document from the RAG system.

    Removes both the file from blob storage and its metadata.
    Returns confirmation with the deleted document's details.
    """
    # Build input DTO
    input_dto = DeleteDocumentInput(
        tenant_id=tenant_id,
        file_id=id,
    )

    # Execute use case
    output = await use_case.execute(input_dto)

    # Map to response
    return DeleteDocumentResponse(
        file_id=output.file_id,
        filename=output.filename,
        deleted_at=output.deleted_at,
        message=output.message,
    )


@router.get(
    "/{id}",
    response_model=DocumentSchema,
    summary="Get a document",
    description="Retrieve a single document by ID.",
)
@inject
async def get_document(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=["api.read"])],
    id: str,
    tenant_id: TenantId,
    document_store=Depends(Provide[Container.document_repository]),
) -> DocumentSchema:
    """
    Get a document by ID.

    Returns the document metadata including upload/update timestamps and custom metadata.
    """
    doc = await document_store.get_by_id(tenant_id=tenant_id, file_id=id)

    if doc is None:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "DocumentNotFound",
                "message": f"Document with ID '{id}' not found",
            },
        )

    # Build metadata response from DocumentMetadata (single SQL source of truth)
    metadata_dict = doc.metadata.model_dump(exclude={"file_id"})

    return DocumentSchema(
        file_id=doc.document.file_id,
        filename=doc.document.blob_name,
        size_bytes=doc.document.size_bytes,
        mime_type=doc.document.content_type,
        created_at=doc.document.upload_timestamp,
        updated_at=doc.document.last_updated,
        metadata=MetadataSchema(**metadata_dict),
    )


@router.get(
    "",
    response_model=ListDocumentsResponse,
    summary="List documents",
    description="List documents with filtering, sorting, and pagination support.",
)
@inject
async def list_documents(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=["api.read"])],
    tenant_id: TenantId,
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Number of items per page"),
    ] = 20,
    cursor: Annotated[
        str | None,
        Query(description="Pagination cursor for next/previous page"),
    ] = None,
    document_type: Annotated[
        str | None,
        Query(description="Filter by document type"),
    ] = None,
    tags: Annotated[
        str | None,
        Query(description="Filter by tags (comma-separated)"),
    ] = None,
    source: Annotated[
        str | None,
        Query(description="Filter by source"),
    ] = None,
    department: Annotated[
        str | None,
        Query(description="Filter by department"),
    ] = None,
    operation_number: Annotated[
        str | None,
        Query(description="Filter by operation number (e.g., UR-P1180)"),
    ] = None,
    country: Annotated[
        str | None,
        Query(description="Filter by country"),
    ] = None,
    sector: Annotated[
        str | None,
        Query(description="Filter by sector (e.g., TRANSPORT)"),
    ] = None,
    disclosed: Annotated[
        bool | None,
        Query(description="Filter by disclosure status"),
    ] = None,
    year: Annotated[
        int | None,
        Query(description="Filter by exact year"),
    ] = None,
    year_min: Annotated[
        int | None,
        Query(description="Filter by minimum year (inclusive)"),
    ] = None,
    year_max: Annotated[
        int | None,
        Query(description="Filter by maximum year (inclusive)"),
    ] = None,
    operation_type: Annotated[
        str | None,
        Query(description="Filter by operation type"),
    ] = None,
    dept_id: Annotated[
        str | None,
        Query(description="Filter by department ID (e.g., INE/TSP)"),
    ] = None,
    document_author: Annotated[
        str | None,
        Query(description="Filter by document author (partial match)"),
    ] = None,
    file_extension: Annotated[
        str | None,
        Query(description="Filter by file extension (e.g., .pdf, pdf)"),
    ] = None,
    access_to_information_policy: Annotated[
        str | None,
        Query(description="Filter by access to information policy"),
    ] = None,
    ezshare_id: Annotated[
        str | None,
        Query(description="Filter by EZSHARE ID"),
    ] = None,
    sort_by: Annotated[
        str,
        Query(description="Sort field (created_at, updated_at, filename, operation_number, year, country, sector)"),
    ] = "created_at",
    sort_order: Annotated[
        str,
        Query(description="Sort order (asc, desc)"),
    ] = "desc",
    use_case: ListDocumentsUseCase = Depends(Provide[Container.list_documents_use_case]),
) -> ListDocumentsResponse:
    """
    List documents with optional filtering and pagination.

    Supports cursor-based pagination for efficient traversal of large datasets.

    JSON Metadata Filters (in-memory):
    - tags, source, department

    Promoted Field Filters (server-side SQL):
    - document_type, operation_number, country, sector, disclosed, year, year_min, year_max
    - operation_type, dept_id, document_author, file_extension
    - access_to_information_policy, ezshare_id

    Sort by: created_at, updated_at, filename, operation_number, year, country, sector
    """
    # Parse tags if provided
    tags_list = None
    if tags:
        tags_list = [t.strip() for t in tags.split(",") if t.strip()]

    # Build input DTO
    input_dto = ListDocumentsInput(
        tenant_id=tenant_id,
        limit=limit,
        cursor=cursor,
        # JSON metadata filters
        document_type=document_type,
        tags=tags_list,
        source=source,
        department=department,
        # Promoted field filters
        operation_number=operation_number,
        country=country,
        sector=sector,
        disclosed=disclosed,
        year=year,
        year_min=year_min,
        year_max=year_max,
        operation_type=operation_type,
        dept_id=dept_id,
        document_author=document_author,
        file_extension=file_extension,
        access_to_information_policy=access_to_information_policy,
        ezshare_id=ezshare_id,
        # Sorting
        sort_by=sort_by,
        sort_order=sort_order,
    )

    # Execute use case
    output = await use_case.execute(input_dto)

    # Map to response
    documents = [
        DocumentSchema(
            file_id=doc.file_id,
            filename=doc.filename,
            size_bytes=doc.size_bytes,
            mime_type=doc.mime_type,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            metadata=MetadataSchema(**doc.metadata.model_dump()),
        )
        for doc in output.documents
    ]

    pagination = PaginationSchema(
        total_count=output.pagination.total_count,
        limit=output.pagination.limit,
        has_next=output.pagination.has_next,
        has_previous=output.pagination.has_previous,
        next_cursor=output.pagination.next_cursor,
        previous_cursor=output.pagination.previous_cursor,
    )

    return ListDocumentsResponse(
        documents=documents,
        pagination=pagination,
    )
