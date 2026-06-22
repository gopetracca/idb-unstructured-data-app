"""List documents use case."""

import base64
import json
from datetime import datetime

from src.application.dto.document_dto import (
    DocumentDTO,
    ListDocumentsInput,
    ListDocumentsOutput,
    PaginationDTO,
)
from src.application.dto.file_index_filters import FileIndexFilters
from src.application.ports.document_query import DocumentQueryPort
from src.core.entities.composites import DocumentComplete
from src.core.value_objects.document_metadata import get_metadata_model


class ListDocumentsUseCase:
    """
    Use case for listing documents with filtering, sorting, and pagination.

    Supports cursor-based pagination for efficient traversal of large datasets.
    """

    def __init__(self, metadata_store: DocumentQueryPort) -> None:
        self._metadata_store = metadata_store

    async def execute(self, input_dto: ListDocumentsInput) -> ListDocumentsOutput:
        """
        Execute the list documents use case with promoted field filtering.

        Applies repository-level filtering on promoted fields, then in-memory
        filtering on JSON metadata fields for optimal performance.
        """
        # Build promoted field filters for server-side filtering
        # document_category selects the metadata model; document_type is user-facing classification
        promoted_filters = FileIndexFilters(
            document_category=input_dto.document_category,
            document_type=input_dto.document_type,
            operation_number=input_dto.operation_number,
            country=input_dto.country,
            sector=input_dto.sector,
            disclosed=input_dto.disclosed,
            year=input_dto.year,
            operation_type=input_dto.operation_type,
            dept_id=input_dto.dept_id,
            document_author=input_dto.document_author,
            file_extension=input_dto.file_extension,
            ezshare_id=input_dto.ezshare_id,
        )

        # Query with server-side promoted field filters
        documents = await self._metadata_store.query_with_filters(
            tenant_id=input_dto.tenant_id,
            filters=promoted_filters,
            max_results=None,
        )

        # Apply JSON metadata filters (in-memory on reduced dataset)
        filtered_documents = self._apply_json_metadata_filters(documents, input_dto)

        # Apply sorting
        sorted_documents = self._apply_sorting(filtered_documents, input_dto)

        # Get total count before pagination
        total_count = len(sorted_documents)

        # Apply cursor-based pagination
        paginated_documents, has_next, has_previous, next_cursor, prev_cursor = (
            self._apply_pagination(sorted_documents, input_dto)
        )

        # Convert to DTOs
        document_dtos = [self._to_document_dto(doc) for doc in paginated_documents]

        pagination = PaginationDTO(
            total_count=total_count,
            limit=input_dto.limit,
            has_next=has_next,
            has_previous=has_previous,
            next_cursor=next_cursor,
            previous_cursor=prev_cursor,
        )

        return ListDocumentsOutput(
            documents=document_dtos,
            pagination=pagination,
        )

    def _apply_json_metadata_filters(
        self,
        documents: list[DocumentComplete],
        input_dto: ListDocumentsInput,
    ) -> list[DocumentComplete]:
        """
        Apply in-memory filters for fields not yet pushed to SQL-level filtering.

        tags, source, and department are now SQL columns on file_metadata,
        but the repository layer doesn't yet filter on them server-side.
        """
        filtered = documents

        for doc in list(filtered):
            metadata = doc.metadata

            # Filter by tags (any match)
            if input_dto.tags:
                doc_tags = metadata.tags or []
                if not any(tag in doc_tags for tag in input_dto.tags):
                    filtered = [d for d in filtered if d != doc]
                    continue

            # Filter by source
            if input_dto.source:
                if metadata.source != input_dto.source:
                    filtered = [d for d in filtered if d != doc]
                    continue

            # Filter by department
            if input_dto.department:
                if metadata.department != input_dto.department:
                    filtered = [d for d in filtered if d != doc]
                    continue

        return filtered

    def _apply_sorting(
        self,
        documents: list[DocumentComplete],
        input_dto: ListDocumentsInput,
    ) -> list[DocumentComplete]:
        """Apply sorting to document list (supports both JSON and promoted fields)."""
        reverse = input_dto.sort_order.lower() == "desc"

        def get_sort_key(doc: DocumentComplete) -> datetime | str | int | None:
            if input_dto.sort_by == "created_at":
                return doc.document.upload_timestamp
            elif input_dto.sort_by == "updated_at":
                return doc.document.last_updated
            elif input_dto.sort_by == "filename":
                return doc.document.blob_name.lower()
            elif input_dto.sort_by == "operation_number":
                return getattr(doc.metadata, "operation_number", None) or ""
            elif input_dto.sort_by == "year":
                return getattr(doc.metadata, "year", None) or 0
            elif input_dto.sort_by == "country":
                return getattr(doc.metadata, "country", None) or ""
            elif input_dto.sort_by == "sector":
                return getattr(doc.metadata, "sector", None) or ""
            else:
                return doc.document.upload_timestamp

        return sorted(documents, key=get_sort_key, reverse=reverse)

    def _apply_pagination(
        self,
        documents: list[DocumentComplete],
        input_dto: ListDocumentsInput,
    ) -> tuple[list[DocumentComplete], bool, bool, str | None, str | None]:
        """Apply cursor-based pagination."""
        start_index = 0
        if input_dto.cursor:
            try:
                cursor_data = json.loads(
                    base64.b64decode(input_dto.cursor).decode("utf-8")
                )
                start_index = cursor_data.get("index", 0)
            except Exception:
                start_index = 0

        end_index = start_index + input_dto.limit
        paginated = documents[start_index:end_index]

        has_previous = start_index > 0
        has_next = end_index < len(documents)

        next_cursor = None
        if has_next:
            next_cursor = base64.b64encode(
                json.dumps({"index": end_index}).encode("utf-8")
            ).decode("utf-8")

        prev_cursor = None
        if has_previous:
            prev_index = max(0, start_index - input_dto.limit)
            prev_cursor = base64.b64encode(
                json.dumps({"index": prev_index}).encode("utf-8")
            ).decode("utf-8")

        return paginated, has_next, has_previous, next_cursor, prev_cursor

    def _to_document_dto(self, doc: DocumentComplete) -> DocumentDTO:
        """Convert DocumentComplete to DocumentDTO."""
        return DocumentDTO(
            file_id=doc.document.file_id,
            filename=doc.document.blob_name,
            size_bytes=doc.document.size_bytes,
            mime_type=doc.document.content_type,
            created_at=doc.document.upload_timestamp,
            updated_at=doc.document.last_updated,
            metadata=doc.metadata,
        )
