"""SQL Server repository for ChunkIndex entities."""

import logging
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.entities.chunk_index import ChunkIndex
from src.core.entities.chunk_metadata_index import ChunkMetadataIndex, EmbeddingStatus
from src.infrastructure.sqlserver.models.chunk_metadata_model import ChunkMetadataTable
from src.infrastructure.sqlserver.models.chunk_model import ChunkTable
from src.infrastructure.sqlserver.models.chunk_vector_ref_model import ChunkVectorRefTable

logger = logging.getLogger(__name__)


class ChunkIndexRepositorySQLServer:
    """Repository for managing ChunkIndex entities in SQL Server.

    Backed by the `chunks` + `chunk_metadata` + `chunk_vector_refs` tables.

    Parent fields (tenant_id, file_version) are no longer stored on chunks;
    they are derived via JOIN to the `files` table when needed.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def close(self) -> None:
        """No-op: session lifecycle is managed per-request."""
        pass

    async def create(self, chunk_index: ChunkIndex) -> ChunkIndex:
        """Create a new ChunkIndex entity with a default chunk_metadata record."""
        async with self._session_factory() as session:
            row = ChunkTable.from_entity(chunk_index)
            meta_row = ChunkMetadataTable(
                chunk_id=chunk_index.chunk_id,
                embedding_status=EmbeddingStatus.PENDING.value,
                metadata_json=chunk_index.metadata_json,
            )
            row.metadata_record = meta_row
            session.add(row)
            await session.commit()
            return chunk_index

    async def get_by_id(self, chunk_id: str) -> ChunkIndex | None:
        """Get a ChunkIndex by its chunk_id."""
        async with self._session_factory() as session:
            stmt = sa.select(ChunkTable).where(ChunkTable.chunk_id == chunk_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return row.to_entity()

    async def get_metadata_by_id(self, chunk_id: str) -> ChunkMetadataIndex | None:
        """Get chunk metadata by chunk_id."""
        async with self._session_factory() as session:
            stmt = sa.select(ChunkMetadataTable).where(
                ChunkMetadataTable.chunk_id == chunk_id
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return row.to_entity()

    async def update(self, chunk_index: ChunkIndex) -> ChunkIndex:
        """Update an existing ChunkIndex entity."""
        async with self._session_factory() as session:
            stmt = sa.select(ChunkTable).where(
                ChunkTable.chunk_id == chunk_index.chunk_id
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                raise ValueError(f"ChunkIndex not found: chunk_id={chunk_index.chunk_id}")

            row.update_from_entity(chunk_index)
            await session.commit()
            return chunk_index

    async def upsert(self, chunk_index: ChunkIndex) -> ChunkIndex:
        """Create or update a ChunkIndex entity (atomic single-session)."""
        async with self._session_factory() as session:
            stmt = sa.select(ChunkTable).where(
                ChunkTable.chunk_id == chunk_index.chunk_id
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()

            if row is None:
                row = ChunkTable.from_entity(chunk_index)
                meta_row = ChunkMetadataTable(
                    chunk_id=chunk_index.chunk_id,
                    embedding_status=EmbeddingStatus.PENDING.value,
                    metadata_json=chunk_index.metadata_json,
                )
                row.metadata_record = meta_row
                session.add(row)
            else:
                row.update_from_entity(chunk_index)

            await session.commit()
            return chunk_index

    async def delete(self, chunk_id: str) -> bool:
        """Delete a ChunkIndex entity."""
        async with self._session_factory() as session:
            stmt = sa.delete(ChunkTable).where(ChunkTable.chunk_id == chunk_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def batch_create(self, chunks: list[ChunkIndex]) -> list[ChunkIndex]:
        """Create multiple chunks in a single transaction (with metadata records)."""
        if not chunks:
            return []

        async with self._session_factory() as session:
            for chunk in chunks:
                row = ChunkTable.from_entity(chunk)
                meta_row = ChunkMetadataTable(
                    chunk_id=chunk.chunk_id,
                    embedding_status=EmbeddingStatus.PENDING.value,
                    metadata_json=chunk.metadata_json,
                )
                row.metadata_record = meta_row
                session.add(row)
            await session.commit()
            return chunks

    async def query_by_file(
        self,
        file_id: str,
        limit: int | None = None,
    ) -> list[ChunkIndex]:
        """Query all chunks for a file."""
        async with self._session_factory() as session:
            stmt = (
                sa.select(ChunkTable)
                .where(ChunkTable.file_id == file_id)
                .order_by(ChunkTable.chunk_index)
            )
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return [row.to_entity() for row in result.scalars().all()]

    async def query_by_file_page(
        self,
        file_id: str,
        offset: int,
        limit: int,
    ) -> list[ChunkIndex]:
        """Query a page of chunks for a file."""
        async with self._session_factory() as session:
            stmt = (
                sa.select(ChunkTable)
                .where(ChunkTable.file_id == file_id)
                .order_by(ChunkTable.chunk_index)
                .offset(offset)
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [row.to_entity() for row in result.scalars().all()]

    async def query_by_embedding_status(
        self,
        file_id: str,
        status: EmbeddingStatus,
        limit: int | None = None,
    ) -> list[ChunkIndex]:
        """Query chunks by embedding status (via chunk_metadata JOIN)."""
        async with self._session_factory() as session:
            stmt = (
                sa.select(ChunkTable)
                .join(
                    ChunkMetadataTable,
                    ChunkTable.chunk_id == ChunkMetadataTable.chunk_id,
                )
                .where(
                    ChunkTable.file_id == file_id,
                    ChunkMetadataTable.embedding_status == status.value,
                )
                .order_by(ChunkTable.chunk_index)
            )
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return [row.to_entity() for row in result.scalars().all()]

    async def query_pending_embeddings(
        self,
        file_id: str,
        limit: int | None = None,
    ) -> list[ChunkIndex]:
        """Query chunks with pending embeddings."""
        return await self.query_by_embedding_status(
            file_id, EmbeddingStatus.PENDING, limit
        )

    async def delete_by_file(self, file_id: str) -> int:
        """Delete all chunks for a file."""
        async with self._session_factory() as session:
            stmt = sa.delete(ChunkTable).where(ChunkTable.file_id == file_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    async def count_by_file(self, file_id: str) -> int:
        """Count all chunks for a file."""
        async with self._session_factory() as session:
            stmt = (
                sa.select(sa.func.count())
                .select_from(ChunkTable)
                .where(ChunkTable.file_id == file_id)
            )
            result = await session.execute(stmt)
            return result.scalar_one()

    async def count_embedded(self, file_id: str) -> int:
        """Count chunks with completed embeddings."""
        async with self._session_factory() as session:
            stmt = (
                sa.select(sa.func.count())
                .select_from(ChunkTable)
                .join(
                    ChunkMetadataTable,
                    ChunkTable.chunk_id == ChunkMetadataTable.chunk_id,
                )
                .where(
                    ChunkTable.file_id == file_id,
                    ChunkMetadataTable.embedding_status == EmbeddingStatus.COMPLETED.value,
                )
            )
            result = await session.execute(stmt)
            return result.scalar_one()

    async def mark_embedded(
        self,
        chunk_id: str,
        vector_db_id: str,
        db_name: str = "azure-ai-search",
    ) -> ChunkIndex | None:
        """Mark a chunk as embedded with vector DB reference.

        Updates the chunk_metadata status and inserts a vector ref record.
        """
        async with self._session_factory() as session:
            # Check chunk exists
            stmt = sa.select(ChunkTable).where(ChunkTable.chunk_id == chunk_id)
            result = await session.execute(stmt)
            chunk_row = result.scalar_one_or_none()
            if chunk_row is None:
                return None

            # Update metadata
            meta_stmt = sa.select(ChunkMetadataTable).where(
                ChunkMetadataTable.chunk_id == chunk_id
            )
            meta_result = await session.execute(meta_stmt)
            meta_row = meta_result.scalar_one_or_none()
            if meta_row:
                meta_row.embedding_status = EmbeddingStatus.COMPLETED.value
            else:
                meta_row = ChunkMetadataTable(
                    chunk_id=chunk_id,
                    embedding_status=EmbeddingStatus.COMPLETED.value,
                )
                session.add(meta_row)

            # Insert vector ref record
            vector_ref = ChunkVectorRefTable(
                chunk_id=chunk_id,
                db_name=db_name,
                vector_doc_id=vector_db_id,
            )
            session.add(vector_ref)

            await session.commit()
            return chunk_row.to_entity()

    async def mark_failed(self, chunk_id: str) -> ChunkIndex | None:
        """Mark a chunk's embedding as failed."""
        async with self._session_factory() as session:
            # Check chunk exists
            stmt = sa.select(ChunkTable).where(ChunkTable.chunk_id == chunk_id)
            result = await session.execute(stmt)
            chunk_row = result.scalar_one_or_none()
            if chunk_row is None:
                return None

            # Update metadata
            meta_stmt = sa.select(ChunkMetadataTable).where(
                ChunkMetadataTable.chunk_id == chunk_id
            )
            meta_result = await session.execute(meta_stmt)
            meta_row = meta_result.scalar_one_or_none()
            if meta_row:
                meta_row.embedding_status = EmbeddingStatus.FAILED.value
            else:
                meta_row = ChunkMetadataTable(
                    chunk_id=chunk_id,
                    embedding_status=EmbeddingStatus.FAILED.value,
                )
                session.add(meta_row)

            await session.commit()
            return chunk_row.to_entity()

    async def update_blob_references(
        self,
        chunk_id: str,
        chunk_blob_ref: str | None = None,
        embedding_blob_ref: str | None = None,
    ) -> ChunkIndex | None:
        """Update blob storage references for a chunk (atomic single-session)."""
        async with self._session_factory() as session:
            stmt = sa.select(ChunkTable).where(ChunkTable.chunk_id == chunk_id)
            result = await session.execute(stmt)
            chunk_row = result.scalar_one_or_none()
            if chunk_row is None:
                return None

            if chunk_blob_ref is not None:
                chunk_row.chunk_blob_ref = chunk_blob_ref
            if embedding_blob_ref is not None:
                chunk_row.embedding_blob_ref = embedding_blob_ref

            entity = chunk_row.to_entity()
            await session.commit()
            return entity

    async def batch_get_metadata(self, chunk_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Return {chunk_id: metadata_json} for the given chunk IDs (single IN query)."""
        if not chunk_ids:
            return {}
        async with self._session_factory() as session:
            stmt = sa.select(
                ChunkMetadataTable.chunk_id,
                ChunkMetadataTable.metadata_json,
            ).where(ChunkMetadataTable.chunk_id.in_(chunk_ids))
            result = await session.execute(stmt)
            return {row.chunk_id: row.metadata_json for row in result.all()}

    async def get_chunk_ids_for_db(
        self,
        file_id: str,
        db_name: str = "azure-ai-search",
    ) -> list[str]:
        """Get all vector DB document IDs for a file's chunks."""
        async with self._session_factory() as session:
            stmt = (
                sa.select(ChunkVectorRefTable.vector_doc_id)
                .join(ChunkTable, ChunkVectorRefTable.chunk_id == ChunkTable.chunk_id)
                .where(
                    ChunkTable.file_id == file_id,
                    ChunkVectorRefTable.db_name == db_name,
                )
            )
            result = await session.execute(stmt)
            return [row[0] for row in result.all()]
