"""Unit tests for ListChunksUseCase."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.dto.chunking import ListChunksRequest
from src.application.use_cases.list_chunks import ListChunksUseCase
from src.core.entities.chunk_index import ChunkIndex
from src.core.errors import DocumentNotFoundError


@pytest.mark.unit
class TestListChunksUseCase:
    """Tests for list chunks pagination behavior."""

    async def test_execute_returns_empty_when_no_chunks(self) -> None:
        chunk_index_store = MagicMock()
        file_index_store = MagicMock()
        file_index_store.get_by_id = AsyncMock(return_value=MagicMock())
        chunk_index_store.count_by_file = AsyncMock(return_value=0)
        chunk_index_store.query_by_file_page = AsyncMock(return_value=[])

        use_case = ListChunksUseCase(
            chunk_index_store=chunk_index_store,
            file_index_store=file_index_store,
        )

        result = await use_case.execute(
            ListChunksRequest(file_id="file-1", tenant_id="default", page=1, page_size=20)
        )

        assert result.file_id == "file-1"
        assert result.chunk_count == 0
        assert result.total_pages == 0
        assert result.chunks == []
        file_index_store.get_by_id.assert_awaited_once_with(
            tenant_id="default",
            file_id="file-1",
        )
        chunk_index_store.query_by_file_page.assert_not_called()

    async def test_execute_applies_pagination(self) -> None:
        chunk_index_store = MagicMock()
        file_index_store = MagicMock()
        file_index_store.get_by_id = AsyncMock(return_value=MagicMock())
        chunk_index_store.count_by_file = AsyncMock(return_value=5)
        chunk_index_store.query_by_file_page = AsyncMock(
            return_value=[
                ChunkIndex(
                    file_id="file-1",
                    chunk_id=f"file-1_chunk_{i}",
                    chunk_index=i,
                    text_preview=f"chunk {i}",
                    start_char=i * 10,
                    end_char=(i + 1) * 10,
                    page_number=1,
                )
                for i in [2, 3]
            ]
        )

        use_case = ListChunksUseCase(
            chunk_index_store=chunk_index_store,
            file_index_store=file_index_store,
        )

        result = await use_case.execute(
            ListChunksRequest(file_id="file-1", tenant_id="default", page=2, page_size=2)
        )

        assert result.chunk_count == 5
        assert result.total_pages == 3
        assert result.page == 2
        assert result.page_size == 2
        assert [chunk.chunk_index for chunk in result.chunks] == [2, 3]
        chunk_index_store.count_by_file.assert_awaited_once_with(file_id="file-1")
        chunk_index_store.query_by_file_page.assert_awaited_once_with(
            file_id="file-1",
            offset=2,
            limit=2,
        )

    async def test_execute_raises_not_found_when_file_not_owned(self) -> None:
        chunk_index_store = MagicMock()
        file_index_store = MagicMock()
        file_index_store.get_by_id = AsyncMock(return_value=None)

        use_case = ListChunksUseCase(
            chunk_index_store=chunk_index_store,
            file_index_store=file_index_store,
        )

        with pytest.raises(DocumentNotFoundError):
            await use_case.execute(
                ListChunksRequest(
                    file_id="file-1",
                    tenant_id="default",
                    page=1,
                    page_size=20,
                )
            )

        chunk_index_store.count_by_file.assert_not_called()

    async def test_execute_last_partial_page(self) -> None:
        chunk_index_store = MagicMock()
        file_index_store = MagicMock()
        file_index_store.get_by_id = AsyncMock(return_value=MagicMock())
        chunk_index_store.count_by_file = AsyncMock(return_value=5)
        chunk_index_store.query_by_file_page = AsyncMock(
            return_value=[
                ChunkIndex(
                    file_id="file-1",
                    chunk_id="file-1_chunk_4",
                    chunk_index=4,
                    text_preview="chunk 4",
                    start_char=40,
                    end_char=50,
                    page_number=1,
                )
            ]
        )

        use_case = ListChunksUseCase(
            chunk_index_store=chunk_index_store,
            file_index_store=file_index_store,
        )

        result = await use_case.execute(
            ListChunksRequest(file_id="file-1", tenant_id="default", page=3, page_size=2)
        )

        assert result.chunk_count == 5
        assert result.total_pages == 3
        assert result.page == 3
        assert [chunk.chunk_index for chunk in result.chunks] == [4]
        chunk_index_store.query_by_file_page.assert_awaited_once_with(
            file_id="file-1",
            offset=4,
            limit=2,
        )

    async def test_execute_page_beyond_total_returns_empty_chunks(self) -> None:
        chunk_index_store = MagicMock()
        file_index_store = MagicMock()
        file_index_store.get_by_id = AsyncMock(return_value=MagicMock())
        chunk_index_store.count_by_file = AsyncMock(return_value=5)
        chunk_index_store.query_by_file_page = AsyncMock(return_value=[])

        use_case = ListChunksUseCase(
            chunk_index_store=chunk_index_store,
            file_index_store=file_index_store,
        )

        result = await use_case.execute(
            ListChunksRequest(file_id="file-1", tenant_id="default", page=4, page_size=2)
        )

        assert result.chunk_count == 5
        assert result.total_pages == 3
        assert result.page == 4
        assert result.chunks == []
        chunk_index_store.query_by_file_page.assert_awaited_once_with(
            file_id="file-1",
            offset=6,
            limit=2,
        )

    async def test_execute_exact_boundary_page(self) -> None:
        chunk_index_store = MagicMock()
        file_index_store = MagicMock()
        file_index_store.get_by_id = AsyncMock(return_value=MagicMock())
        chunk_index_store.count_by_file = AsyncMock(return_value=6)
        chunk_index_store.query_by_file_page = AsyncMock(
            return_value=[
                ChunkIndex(
                    file_id="file-1",
                    chunk_id="file-1_chunk_4",
                    chunk_index=4,
                    text_preview="chunk 4",
                    start_char=40,
                    end_char=50,
                    page_number=1,
                ),
                ChunkIndex(
                    file_id="file-1",
                    chunk_id="file-1_chunk_5",
                    chunk_index=5,
                    text_preview="chunk 5",
                    start_char=50,
                    end_char=60,
                    page_number=1,
                ),
            ]
        )

        use_case = ListChunksUseCase(
            chunk_index_store=chunk_index_store,
            file_index_store=file_index_store,
        )

        result = await use_case.execute(
            ListChunksRequest(file_id="file-1", tenant_id="default", page=3, page_size=2)
        )

        assert result.chunk_count == 6
        assert result.total_pages == 3
        assert result.page == 3
        assert [chunk.chunk_index for chunk in result.chunks] == [4, 5]
        chunk_index_store.query_by_file_page.assert_awaited_once_with(
            file_id="file-1",
            offset=4,
            limit=2,
        )
