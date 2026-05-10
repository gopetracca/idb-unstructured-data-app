"""Use case for ingesting vectorized documents into collections."""

import logging
import time

from src.application.dto.ingestion_dto import (
    IngestDocumentsInput,
    IngestDocumentsOutput,
    IngestionDocument,
)
from src.application.ports.document_store import DocumentStorePort
from src.application.ports.processing_events import ProcessingEventsPort
from src.application.ports.vector_database import VectorDatabasePort
from src.core.entities.composites import DocumentComplete
from src.core.entities.pipeline_state import ProcessingStage
from src.core.entities.vector_document import VectorDocument
from src.core.errors import (
    IndexNotFoundError,
    VectorDatabaseError,
    VectorDimensionMismatchError,
)
from src.core.value_objects.searchable_metadata import SearchableMetadata

logger = logging.getLogger(__name__)


class IngestDocumentsUseCase:
    """
    Use case for ingesting vectorized documents into a collection.

    Validates vector dimensions, transforms input to VectorDocument entities,
    assembles typed SearchableMetadata from DocumentMetadata + chunk data, and
    performs batch upsert operations.
    """

    def __init__(
        self,
        vector_database: VectorDatabasePort,
        document_store: DocumentStorePort,
        processing_events: ProcessingEventsPort | None = None,
    ) -> None:
        self._vector_db = vector_database
        self._document_store = document_store
        self._processing_events = processing_events

    async def close(self) -> None:
        """Release any underlying client resources."""
        close_fn = getattr(self._vector_db, "close", None)
        if callable(close_fn):
            await close_fn()

    async def execute(
        self, input_dto: IngestDocumentsInput
    ) -> IngestDocumentsOutput:
        """
        Ingest documents into the specified collection.

        Raises:
            IndexNotFoundError: If collection doesn't exist
            VectorDimensionMismatchError: If vector dimensions don't match
            VectorDatabaseError: If ingestion fails
        """
        start_time = time.time()

        unique_file_ids = {doc.file_id for doc in input_dto.documents}

        logger.info(
            f"Ingesting {len(input_dto.documents)} documents into "
            f"collection '{input_dto.collection_name}', "
            f"correlation_id={input_dto.correlation_id}"
        )

        try:
            # Get collection info to validate vector dimensions and embedding model
            collection_info = await self._vector_db.get_index(
                input_dto.collection_name
            )
            expected_dimension = collection_info["vector_dimension"]
            expected_embedding_model = collection_info.get(
                "embedding_model", "text-embedding-3-small"
            )

            logger.debug(
                f"Expected vector dimension: {expected_dimension}, "
                f"expected embedding model: {expected_embedding_model}, "
                f"correlation_id={input_dto.correlation_id}"
            )

            # Validate all document vectors have correct dimension
            invalid_docs = []
            for doc in input_dto.documents:
                if len(doc.vector) != expected_dimension:
                    invalid_docs.append(
                        f"{doc.id} (dim={len(doc.vector)}, expected={expected_dimension})"
                    )

            if invalid_docs:
                error_msg = (
                    f"Vector dimension mismatch for {len(invalid_docs)} documents: "
                    f"{', '.join(invalid_docs[:5])}"
                )
                if len(invalid_docs) > 5:
                    error_msg += f" and {len(invalid_docs) - 5} more"

                logger.error(
                    f"{error_msg}, correlation_id={input_dto.correlation_id}"
                )
                raise VectorDimensionMismatchError(
                    expected_dimension=expected_dimension,
                    actual_dimension=len(input_dto.documents[0].vector)
                    if input_dto.documents
                    else 0,
                    index_name=input_dto.collection_name,
                )

            # Fetch document metadata for all unique file_ids
            file_metadata_map = await self._fetch_file_metadata(
                tenant_id=input_dto.tenant_id,
                file_ids=unique_file_ids,
                correlation_id=input_dto.correlation_id,
            )

            # Transform IngestionDocument DTOs to VectorDocument entities
            vector_documents = []
            for doc in input_dto.documents:
                doc_complete = file_metadata_map.get(doc.file_id)
                searchable = self._build_searchable_metadata(
                    chunk_metadata=doc.metadata,
                    doc_complete=doc_complete,
                    collection_name=input_dto.collection_name,
                )

                vector_doc = VectorDocument(
                    id=doc.id,
                    chunk_id=doc.chunk_id,
                    file_id=doc.file_id,
                    text=doc.text,
                    vector=doc.vector,
                    metadata=searchable,
                )
                vector_documents.append(vector_doc)

            # Upsert documents (returns list of successful IDs)
            successful_ids = await self._vector_db.upsert_documents(
                input_dto.collection_name, vector_documents
            )

            # Calculate results
            total = len(input_dto.documents)
            successful = len(successful_ids)
            failed = total - successful

            # Determine failed IDs
            all_ids = {doc.id for doc in input_dto.documents}
            failed_ids = list(all_ids - set(successful_ids))

            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)

            logger.info(
                f"Ingestion completed: {successful}/{total} successful, "
                f"{failed} failed, time={processing_time_ms}ms, "
                f"correlation_id={input_dto.correlation_id}"
            )

            if failed > 0:
                logger.warning(
                    f"Failed to ingest {failed} documents: {failed_ids[:10]}, "
                    f"correlation_id={input_dto.correlation_id}"
                )

            await self._log_processing_events(
                tenant_id=input_dto.tenant_id,
                file_ids=unique_file_ids,
                documents=input_dto.documents,
                duration_ms=processing_time_ms,
                failed_ids=failed_ids if failed > 0 else None,
                error_message=None,
            )

            return IngestDocumentsOutput(
                collection_name=input_dto.collection_name,
                total_documents=total,
                successful=successful,
                failed=failed,
                failed_ids=failed_ids,
                processing_time_ms=processing_time_ms,
                correlation_id=input_dto.correlation_id,
            )

        except IndexNotFoundError:
            logger.warning(
                f"Collection '{input_dto.collection_name}' not found, "
                f"correlation_id={input_dto.correlation_id}"
            )
            raise

        except VectorDimensionMismatchError:
            raise

        except Exception as e:
            processing_time_ms = int((time.time() - start_time) * 1000)
            await self._log_processing_events(
                tenant_id=input_dto.tenant_id,
                file_ids=unique_file_ids,
                documents=input_dto.documents,
                duration_ms=processing_time_ms,
                failed_ids=None,
                error_message=str(e),
            )
            logger.error(
                f"Failed to ingest documents into '{input_dto.collection_name}': {e}, "
                f"correlation_id={input_dto.correlation_id}",
                exc_info=True,
            )
            raise VectorDatabaseError(
                f"Document ingestion failed: {e}",
                index_name=input_dto.collection_name,
                operation="ingest_documents",
            )

    def _build_searchable_metadata(
        self,
        chunk_metadata: dict,
        doc_complete: DocumentComplete | None,
        collection_name: str,
    ) -> SearchableMetadata:
        """Assemble SearchableMetadata from DocumentMetadata + chunk-level dict."""
        if not doc_complete:
            return SearchableMetadata.from_document_and_chunk(
                doc_metadata=object(),
                chunk_metadata=chunk_metadata,
                collection_name=collection_name,
            )

        return SearchableMetadata.from_document_and_chunk(
            doc_metadata=doc_complete.metadata,
            chunk_metadata=chunk_metadata,
            ezshare_id=doc_complete.document.ezshare_id,
            collection_name=collection_name,
            blob_name=doc_complete.document.blob_name,
        )

    async def _log_processing_events(
        self,
        tenant_id: str,
        file_ids: set[str],
        documents: list[IngestionDocument],
        duration_ms: int,
        failed_ids: list[str] | None,
        error_message: str | None,
    ) -> None:
        if not self._processing_events:
            return
        if not file_ids:
            return

        failed_id_set = set(failed_ids or [])
        totals: dict[str, int] = {}
        failed_counts: dict[str, int] = {}

        for doc in documents:
            totals[doc.file_id] = totals.get(doc.file_id, 0) + 1
            if doc.id in failed_id_set:
                failed_counts[doc.file_id] = failed_counts.get(doc.file_id, 0) + 1

        for file_id in file_ids:
            total = totals.get(file_id, 0)
            failed = failed_counts.get(file_id, 0)
            status = "success" if failed == 0 and error_message is None else "failed"
            message = error_message
            if message is None and failed > 0:
                message = f"{failed}/{total} documents failed to ingest"
            try:
                await self._processing_events.log_stage_event(
                    file_id=file_id,
                    tenant_id=tenant_id,
                    stage=ProcessingStage.INGEST.value,
                    status=status,
                    duration_ms=duration_ms,
                    error_message=message,
                )
            except Exception:
                logger.warning("Failed to log stage event", exc_info=True)

    async def _fetch_file_metadata(
        self, tenant_id: str, file_ids: set[str], correlation_id: str
    ) -> dict[str, DocumentComplete]:
        """Fetch DocumentComplete entities for multiple file IDs."""
        file_metadata_map: dict[str, DocumentComplete] = {}

        for file_id in file_ids:
            try:
                doc_complete = await self._document_store.get_by_id(
                    tenant_id=tenant_id, file_id=file_id
                )
                if doc_complete:
                    file_metadata_map[file_id] = doc_complete
                else:
                    logger.warning(
                        f"Document not found for file_id '{file_id}', "
                        f"correlation_id={correlation_id}"
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to fetch document for file_id '{file_id}': {e}, "
                    f"correlation_id={correlation_id}"
                )

        logger.info(
            f"Fetched document metadata for {len(file_metadata_map)}/{len(file_ids)} files, "
            f"correlation_id={correlation_id}"
        )

        return file_metadata_map
