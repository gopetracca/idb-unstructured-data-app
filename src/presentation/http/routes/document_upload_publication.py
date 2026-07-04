"""Publication document upload API route.

Type-specific endpoint for uploading research publications (journals, working papers, etc.)
with strongly-typed form fields for publication metadata.
"""

from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, File, Security, UploadFile

from src.application.dto.document_dto import UploadDocumentInput
from src.config.settings import get_settings
from src.application.use_cases.upload_and_enqueue_document import (
    UploadAndEnqueueDocumentUseCase,
)
from src.container import Container
from src.presentation.http.auth import CurrentUser, Scopes, get_current_user
from src.presentation.http.schemas.chunking import UploadChunkingStrategyForm
from src.presentation.http.schemas.document_schemas import (
    MetadataSchema,
    UploadDocumentResponse,
)
from src.presentation.http.routes.upload_helpers import read_upload_bounded
from src.presentation.http.schemas.document_upload_schemas import (
    PublicationDocumentUploadForm,
)
from src.presentation.http.tenant import TenantId

router = APIRouter(prefix="/api/v1/documents", tags=["document-management"])


@router.post(
    "/publication",
    response_model=UploadDocumentResponse,
    status_code=201,
    summary="Upload a publication document",
    description="Upload a research publication with typed metadata fields.",
)
@inject
async def upload_publication_document(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=[Scopes.DOCUMENTS_WRITE])],
    file: Annotated[UploadFile, File(description="PDF or Word document to upload")],
    tenant_id: TenantId,
    form_data: PublicationDocumentUploadForm = Depends(
        PublicationDocumentUploadForm.as_form
    ),
    chunking_strategy: UploadChunkingStrategyForm = Depends(
        UploadChunkingStrategyForm.as_form
    ),
    use_case: UploadAndEnqueueDocumentUseCase = Depends(
        Provide[Container.upload_and_enqueue_document_use_case]
    ),
) -> UploadDocumentResponse:
    """
    Upload a research publication to the RAG system.

    Accepts PDF and Word (.docx) files up to the configured size limit
    (FILE_UPLOAD_MAX_FILE_SIZE_MB, default 50 MB) with typed publication metadata.
    Requires a unique ezshare_id for duplicate detection.

    Publication-specific fields:
    - journal: Journal or publication venue name
    - doi: Digital Object Identifier
    - issn: International Standard Serial Number
    - peer_reviewed: Whether the publication was peer-reviewed
    - publication_type: Type of publication (journal_article, working_paper, book_chapter)
    - publication_date: Date of publication

    Returns the generated file ID and upload confirmation.
    """
    # Read file content in bounded chunks (413 past the configured limit)
    content = await read_upload_bounded(
        file, get_settings().file_upload.max_file_size_bytes
    )

    # Build metadata from typed form fields
    metadata_dict = form_data.to_metadata_dict()

    chunking_strategy_model = chunking_strategy.to_chunking_strategy()

    # Build input DTO
    input_dto = UploadDocumentInput(
        tenant_id=tenant_id,
        filename=file.filename or "unknown",
        content=content,
        content_type=file.content_type or "application/octet-stream",
        collection_name=form_data.collection_name,
        ezshare_id=form_data.ezshare_id,
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
