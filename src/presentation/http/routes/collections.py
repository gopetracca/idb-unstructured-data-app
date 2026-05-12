"""Collection management HTTP routes."""

import logging
import uuid
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Header, HTTPException, Security, status

from src.application.dto.collection_dto import (
    ConfigureRerankerInput,
    CreateCollectionInput,
    DeleteCollectionInput,
    GetCollectionInput,
)
from src.application.dto.ingestion_dto import (
    IngestDocumentsInput,
    IngestionDocument,
)
from src.application.use_cases.ingest_documents import IngestDocumentsUseCase
from src.application.use_cases.manage_collection import ManageCollectionUseCase
from src.container import Container
from src.presentation.http.auth import CurrentUser, get_current_user
from src.core.errors import (
    IndexAlreadyExistsError,
    IndexNotFoundError,
    VectorDatabaseError,
    VectorDimensionMismatchError,
)
from src.presentation.http.schemas.collection_schemas import (
    CollectionSchema,
    ConfigureRerankerRequest,
    ConfigureRerankerResponse,
    CreateCollectionRequest,
    CreateCollectionResponse,
    DeleteCollectionResponse,
    GetCollectionResponse,
    IngestDocumentsRequest,
    IngestDocumentsResponse,
    ListCollectionsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/collections", tags=["collections"])


@router.post(
    "",
    response_model=CreateCollectionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {
            "description": "Collection created successfully",
            "model": CreateCollectionResponse,
        },
        400: {
            "description": "Invalid request parameters",
        },
        409: {
            "description": "Collection already exists",
        },
        500: {
            "description": "Internal server error",
        },
        503: {
            "description": "Service not initialized",
        },
    },
    summary="Create collection",
    description="""
    Create a new vector search collection with specified configuration.

    The collection is created with:
    - A unique name
    - Vector dimension size (must match embedding model output)
    - Optional description

    Collections use Azure AI Search's HNSW algorithm for efficient vector search.
    """,
)
@inject
async def create_collection(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=["api.write"])],
    request: CreateCollectionRequest,
    x_tenant_id: Annotated[
        str,
        Header(description="Tenant identifier"),
    ] = "default",
    use_case: ManageCollectionUseCase = Depends(Provide[Container.manage_collection_use_case]),
) -> CreateCollectionResponse:
    """
    Create a new collection.

    Args:
        request: Collection creation request
        x_tenant_id: Tenant identifier from header
        use_case: Injected ManageCollectionUseCase

    Returns:
        CreateCollectionResponse with creation result

    Raises:
        HTTPException: On validation errors, conflicts, or processing errors
    """
    correlation_id = str(uuid.uuid4())

    logger.info(
        f"Received create collection request: name='{request.name}', "
        f"dimension={request.vector_dimension}, embedding_model='{request.embedding_model}', "
        f"correlation_id={correlation_id}"
    )

    try:
        # Convert HTTP schema to application DTO
        input_dto = CreateCollectionInput(
            tenant_id=x_tenant_id,
            name=request.name,
            vector_dimension=request.vector_dimension,
            embedding_model=request.embedding_model,
            document_type=request.document_type,
            description=request.description,
            correlation_id=correlation_id,
        )

        # Execute use case
        output = await use_case.create_collection(input_dto)

        logger.info(
            f"Collection created successfully: name='{request.name}', "
            f"correlation_id={correlation_id}"
        )

        return CreateCollectionResponse(
            name=output.name,
            vector_dimension=output.vector_dimension,
            embedding_model=output.embedding_model,
            status=output.status,
            created_at=output.created_at,
            correlation_id=output.correlation_id,
        )

    except IndexAlreadyExistsError as e:
        logger.warning(
            f"Collection already exists: name='{request.name}', "
            f"correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "IndexAlreadyExistsError",
                "message": f"Collection '{request.name}' already exists",
                "correlation_id": correlation_id,
            },
        )

    except VectorDatabaseError as e:
        logger.error(
            f"Failed to create collection: {e}, correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "VectorDatabaseError",
                "message": "Failed to create collection",
                "correlation_id": correlation_id,
            },
        )

    except Exception as e:
        logger.exception(
            f"Unexpected error creating collection: correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "InternalServerError",
                "message": "An unexpected error occurred",
                "correlation_id": correlation_id,
            },
        )


@router.get(
    "",
    response_model=ListCollectionsResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Collections listed successfully",
            "model": ListCollectionsResponse,
        },
        500: {
            "description": "Internal server error",
        },
        503: {
            "description": "Service not initialized",
        },
    },
    summary="List collections",
    description="""
    List all vector search collections for the tenant.

    Returns collection metadata including:
    - Name
    - Vector dimension
    - Document count
    - Creation timestamp
    """,
)
@inject
async def list_collections(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=["api.read"])],
    x_tenant_id: Annotated[
        str,
        Header(description="Tenant identifier"),
    ] = "default",
    use_case: ManageCollectionUseCase = Depends(Provide[Container.manage_collection_use_case]),
) -> ListCollectionsResponse:
    """
    List all collections.

    Args:
        x_tenant_id: Tenant identifier from header
        use_case: Injected ManageCollectionUseCase

    Returns:
        ListCollectionsResponse with collection list

    Raises:
        HTTPException: On processing errors
    """
    correlation_id = str(uuid.uuid4())

    logger.info(
        f"Received list collections request: tenant='{x_tenant_id}', "
        f"correlation_id={correlation_id}"
    )

    try:
        # Execute use case
        output = await use_case.list_collections(x_tenant_id, correlation_id)

        logger.info(
            f"Listed {output.total_count} collections, "
            f"correlation_id={correlation_id}"
        )

        # Map to response schema
        collections = [
            CollectionSchema(
                name=col.name,
                vector_dimension=col.vector_dimension,
                embedding_model=col.embedding_model,
                document_count=col.document_count,
                created_at=col.created_at,
            )
            for col in output.collections
        ]

        return ListCollectionsResponse(
            collections=collections,
            total_count=output.total_count,
        )

    except VectorDatabaseError as e:
        logger.error(
            f"Failed to list collections: {e}, correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "VectorDatabaseError",
                "message": "Failed to list collections",
                "correlation_id": correlation_id,
            },
        )

    except Exception as e:
        logger.exception(
            f"Unexpected error listing collections: correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "InternalServerError",
                "message": "An unexpected error occurred",
                "correlation_id": correlation_id,
            },
        )


@router.get(
    "/{collection_name}",
    response_model=GetCollectionResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Collection details retrieved successfully",
            "model": GetCollectionResponse,
        },
        404: {
            "description": "Collection not found",
        },
        500: {
            "description": "Internal server error",
        },
        503: {
            "description": "Service not initialized",
        },
    },
    summary="Get collection details",
    description="""
    Get detailed information about a specific collection.

    Returns:
    - Collection name and configuration
    - Document count
    - Schema definition
    - Timestamps
    """,
)
@inject
async def get_collection(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=["api.read"])],
    collection_name: str,
    x_tenant_id: Annotated[
        str,
        Header(description="Tenant identifier"),
    ] = "default",
    use_case: ManageCollectionUseCase = Depends(Provide[Container.manage_collection_use_case]),
) -> GetCollectionResponse:
    """
    Get collection details.

    Args:
        collection_name: Name of the collection
        x_tenant_id: Tenant identifier from header
        use_case: Injected ManageCollectionUseCase

    Returns:
        GetCollectionResponse with collection details

    Raises:
        HTTPException: On not found or processing errors
    """
    correlation_id = str(uuid.uuid4())

    logger.info(
        f"Received get collection request: name='{collection_name}', "
        f"correlation_id={correlation_id}"
    )

    try:
        # Convert HTTP request to application DTO
        input_dto = GetCollectionInput(
            tenant_id=x_tenant_id,
            collection_name=collection_name,
            correlation_id=correlation_id,
        )

        # Execute use case
        output = await use_case.get_collection(input_dto)

        logger.info(
            f"Retrieved collection details: name='{collection_name}', "
            f"correlation_id={correlation_id}"
        )

        return GetCollectionResponse(
            name=output.name,
            vector_dimension=output.vector_dimension,
            embedding_model=output.embedding_model,
            document_count=output.document_count,
            index_schema=output.index_schema,
            created_at=output.created_at,
            last_updated=output.last_updated,
        )

    except IndexNotFoundError as e:
        logger.warning(
            f"Collection not found: name='{collection_name}', "
            f"correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "IndexNotFoundError",
                "message": f"Collection '{collection_name}' not found",
                "correlation_id": correlation_id,
            },
        )

    except VectorDatabaseError as e:
        logger.error(
            f"Failed to get collection: {e}, correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "VectorDatabaseError",
                "message": "Failed to retrieve collection details",
                "correlation_id": correlation_id,
            },
        )

    except Exception as e:
        logger.exception(
            f"Unexpected error getting collection: correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "InternalServerError",
                "message": "An unexpected error occurred",
                "correlation_id": correlation_id,
            },
        )


@router.delete(
    "/{collection_name}",
    response_model=DeleteCollectionResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Collection deleted successfully",
            "model": DeleteCollectionResponse,
        },
        404: {
            "description": "Collection not found",
        },
        500: {
            "description": "Internal server error",
        },
        503: {
            "description": "Service not initialized",
        },
    },
    summary="Delete collection",
    description="""
    Delete a collection and all its documents.

    **Warning:** This operation is irreversible. All documents in the
    collection will be permanently deleted.
    """,
)
@inject
async def delete_collection(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=["api.write"])],
    collection_name: str,
    x_tenant_id: Annotated[
        str,
        Header(description="Tenant identifier"),
    ] = "default",
    use_case: ManageCollectionUseCase = Depends(Provide[Container.manage_collection_use_case]),
) -> DeleteCollectionResponse:
    """
    Delete a collection.

    Args:
        collection_name: Name of the collection to delete
        x_tenant_id: Tenant identifier from header
        use_case: Injected ManageCollectionUseCase

    Returns:
        DeleteCollectionResponse with deletion result

    Raises:
        HTTPException: On not found or processing errors
    """
    correlation_id = str(uuid.uuid4())

    logger.info(
        f"Received delete collection request: name='{collection_name}', "
        f"correlation_id={correlation_id}"
    )

    try:
        # Convert HTTP request to application DTO
        input_dto = DeleteCollectionInput(
            tenant_id=x_tenant_id,
            collection_name=collection_name,
            correlation_id=correlation_id,
        )

        # Execute use case
        output = await use_case.delete_collection(input_dto)

        logger.info(
            f"Collection deleted successfully: name='{collection_name}', "
            f"documents_deleted={output.documents_deleted}, "
            f"correlation_id={correlation_id}"
        )

        return DeleteCollectionResponse(
            name=output.name,
            status=output.status,
            documents_deleted=output.documents_deleted,
            correlation_id=output.correlation_id,
        )

    except IndexNotFoundError as e:
        logger.warning(
            f"Collection not found: name='{collection_name}', "
            f"correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "IndexNotFoundError",
                "message": f"Collection '{collection_name}' not found",
                "correlation_id": correlation_id,
            },
        )

    except VectorDatabaseError as e:
        logger.error(
            f"Failed to delete collection: {e}, correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "VectorDatabaseError",
                "message": "Failed to delete collection",
                "correlation_id": correlation_id,
            },
        )

    except Exception as e:
        logger.exception(
            f"Unexpected error deleting collection: correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "InternalServerError",
                "message": "An unexpected error occurred",
                "correlation_id": correlation_id,
            },
        )


@router.post(
    "/{collection_name}/reranker",
    response_model=ConfigureRerankerResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Reranker configured successfully", "model": ConfigureRerankerResponse},
        404: {"description": "Collection not found"},
        500: {"description": "Internal server error"},
    },
    summary="Configure reranker",
    description="""
    Enable or disable the Azure AI semantic L2 reranker on an existing collection.

    Enabling attaches a `SemanticConfiguration` to the index so that searches
    can use `enable_reranker: true`.  Disabling removes it.

    This operation is safe to call on a live collection — documents are not affected.
    """,
)
@inject
async def configure_reranker(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=["api.write"])],
    collection_name: str,
    request: ConfigureRerankerRequest,
    x_tenant_id: Annotated[
        str,
        Header(description="Tenant identifier"),
    ] = "default",
    use_case: ManageCollectionUseCase = Depends(Provide[Container.manage_collection_use_case]),
) -> ConfigureRerankerResponse:
    correlation_id = str(uuid.uuid4())

    logger.info(
        f"Received configure reranker request: collection='{collection_name}', "
        f"enabled={request.enabled}, correlation_id={correlation_id}"
    )

    try:
        input_dto = ConfigureRerankerInput(
            tenant_id=x_tenant_id,
            collection_name=collection_name,
            enabled=request.enabled,
            semantic_configuration_name=request.semantic_configuration_name,
            correlation_id=correlation_id,
        )
        output = await use_case.configure_reranker(input_dto)

        return ConfigureRerankerResponse(
            collection_name=output.collection_name,
            reranker_enabled=output.reranker_enabled,
            semantic_configuration_name=output.semantic_configuration_name,
            correlation_id=output.correlation_id,
        )

    except IndexNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "IndexNotFoundError",
                "message": f"Collection '{collection_name}' not found",
                "correlation_id": correlation_id,
            },
        )

    except VectorDatabaseError as e:
        logger.error("Failed to configure reranker: %s, correlation_id=%s", e, correlation_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "VectorDatabaseError",
                "message": "Failed to configure reranker",
                "correlation_id": correlation_id,
            },
        )

    except Exception:
        logger.exception("Unexpected error configuring reranker: correlation_id=%s", correlation_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "InternalServerError",
                "message": "An unexpected error occurred",
                "correlation_id": correlation_id,
            },
        )


@router.post(
    "/{collection_name}/documents",
    response_model=IngestDocumentsResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Documents ingested successfully",
            "model": IngestDocumentsResponse,
        },
        400: {
            "description": "Invalid request or vector dimension mismatch",
        },
        404: {
            "description": "Collection not found",
        },
        500: {
            "description": "Internal server error",
        },
        503: {
            "description": "Service not initialized",
        },
    },
    summary="Ingest documents",
    description="""
    Ingest vectorized documents into a collection.

    Documents must:
    - Have vectors matching the collection's dimension
    - Include required fields: id, chunk_id, file_id, text, vector
    - Be in batches of up to 1000 documents

    The endpoint validates vector dimensions and returns detailed
    success/failure status for each document.
    """,
)
@inject
async def ingest_documents(
    user: Annotated[CurrentUser, Security(get_current_user, scopes=["api.write"])],
    collection_name: str,
    request: IngestDocumentsRequest,
    x_tenant_id: Annotated[
        str,
        Header(description="Tenant identifier"),
    ] = "default",
    use_case: IngestDocumentsUseCase = Depends(Provide[Container.ingest_documents_use_case]),
) -> IngestDocumentsResponse:
    """
    Ingest documents into a collection.

    Args:
        collection_name: Name of the target collection
        request: Ingestion request with documents
        x_tenant_id: Tenant identifier from header
        use_case: Injected IngestDocumentsUseCase

    Returns:
        IngestDocumentsResponse with ingestion results

    Raises:
        HTTPException: On validation errors, not found, or processing errors
    """
    correlation_id = str(uuid.uuid4())

    logger.info(
        f"Received ingest documents request: collection='{collection_name}', "
        f"documents={len(request.documents)}, correlation_id={correlation_id}"
    )

    try:
        # Convert HTTP schema to application DTO
        ingestion_docs = [
            IngestionDocument(
                id=doc.id,
                chunk_id=doc.chunk_id,
                file_id=doc.file_id,
                text=doc.text,
                vector=doc.vector,
                metadata=doc.metadata,
            )
            for doc in request.documents
        ]

        input_dto = IngestDocumentsInput(
            tenant_id=x_tenant_id,
            collection_name=collection_name,
            documents=ingestion_docs,
            correlation_id=correlation_id,
        )

        # Execute use case
        output = await use_case.execute(input_dto)

        logger.info(
            f"Document ingestion completed: collection='{collection_name}', "
            f"successful={output.successful}/{output.total_documents}, "
            f"time={output.processing_time_ms}ms, correlation_id={correlation_id}"
        )

        return IngestDocumentsResponse(
            collection_name=output.collection_name,
            total_documents=output.total_documents,
            successful=output.successful,
            failed=output.failed,
            failed_ids=output.failed_ids,
            processing_time_ms=output.processing_time_ms,
            correlation_id=output.correlation_id,
        )

    except IndexNotFoundError as e:
        logger.warning(
            f"Collection not found: name='{collection_name}', "
            f"correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "IndexNotFoundError",
                "message": f"Collection '{collection_name}' not found",
                "correlation_id": correlation_id,
            },
        )

    except VectorDimensionMismatchError as e:
        logger.warning(
            f"Vector dimension mismatch: {e}, correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "VectorDimensionMismatchError",
                "message": str(e),
                "correlation_id": correlation_id,
            },
        )

    except VectorDatabaseError as e:
        logger.error(
            f"Failed to ingest documents: {e}, correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "VectorDatabaseError",
                "message": "Failed to ingest documents",
                "correlation_id": correlation_id,
            },
        )

    except Exception as e:
        logger.exception(
            f"Unexpected error ingesting documents: correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "InternalServerError",
                "message": "An unexpected error occurred",
                "correlation_id": correlation_id,
            },
        )
