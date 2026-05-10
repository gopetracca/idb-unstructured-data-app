"""Use case for listing chunks with pagination."""

import math

from src.application.dto.chunking import ChunkDTO, ListChunksRequest, ListChunksResult
from src.application.ports.chunk_index_store import ChunkIndexStorePort
from src.application.ports.document_store import DocumentStorePort
from src.core.errors import DocumentNotFoundError


class ListChunksUseCase:
    """List chunks for a file using chunk index storage."""

    def __init__(
        self,
        chunk_index_store: ChunkIndexStorePort,
        file_index_store: DocumentStorePort,
    ) -> None:
        self._chunk_index_store = chunk_index_store
        self._file_index_store = file_index_store

    async def execute(self, request: ListChunksRequest) -> ListChunksResult:
        """Return paginated chunks for a file."""
        doc = await self._file_index_store.get_by_id(
            tenant_id=request.tenant_id,
            file_id=request.file_id,
        )
        if doc is None:
            raise DocumentNotFoundError(
                file_id=request.file_id,
                tenant_id=request.tenant_id,
            )

        total_count = await self._chunk_index_store.count_by_file(file_id=request.file_id)
        if total_count == 0:
            return ListChunksResult(
                file_id=request.file_id,
                chunk_count=0,
                chunks=[],
                page=request.page,
                page_size=request.page_size,
                total_pages=0,
            )

        total_pages = math.ceil(total_count / request.page_size)
        offset = (request.page - 1) * request.page_size

        paginated_chunks = await self._chunk_index_store.query_by_file_page(
            file_id=request.file_id,
            offset=offset,
            limit=request.page_size,
        )

        chunks = [
            ChunkDTO(
                chunk_id=chunk.chunk_id,
                chunk_index=chunk.chunk_index,
                text_preview=chunk.text_preview,
                char_count=chunk.end_char - chunk.start_char,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                page_number=chunk.page_number,
            )
            for chunk in paginated_chunks
        ]

        return ListChunksResult(
            file_id=request.file_id,
            chunk_count=total_count,
            chunks=chunks,
            page=request.page,
            page_size=request.page_size,
            total_pages=total_pages,
        )
