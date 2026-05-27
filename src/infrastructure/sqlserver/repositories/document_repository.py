"""SQL Server repository for Document, PipelineState, and DocumentMetadata entities.

Implements DocumentStorePort, PipelineStorePort, and DocumentQueryPort.
Backed by three SQL tables: files, pipeline_state, file_metadata.
"""

import logging

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.dto.file_index_filters import FileIndexFilters
from src.core.entities.composites import DocumentComplete, DocumentWithPipeline
from src.core.entities.document import Document
from src.core.entities.pipeline_state import OverallStatus, PipelineState, ProcessingStage
from src.core.value_objects.document_metadata import DocumentMetadata
from src.infrastructure.sqlserver.models.file_metadata_model import FileMetadataTable
from src.infrastructure.sqlserver.models.file_model import FileTable
from src.infrastructure.sqlserver.models.pipeline_state_model import PipelineStateTable

logger = logging.getLogger(__name__)


class DocumentRepositorySQLServer:
    """Repository for managing documents in SQL Server.

    Backed by the `files`, `pipeline_state`, and `file_metadata` tables.
    Implements DocumentStorePort, PipelineStorePort, and DocumentQueryPort.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def close(self) -> None:
        """No-op: session lifecycle is managed per-request."""
        pass

    # ========================================================================
    # Helper: assemble composites from ORM rows
    # ========================================================================

    @staticmethod
    def _to_document_complete(row: FileTable) -> DocumentComplete:
        """Assemble a DocumentComplete from a FileTable row with joined relations."""
        document = row.to_entity()
        pipeline = row.pipeline_state.to_entity() if row.pipeline_state else PipelineState(file_id=row.file_id)
        metadata = row.metadata_record.to_entity() if row.metadata_record else DocumentMetadata(file_id=row.file_id)
        return DocumentComplete(document=document, pipeline=pipeline, metadata=metadata)

    @staticmethod
    def _to_document_with_pipeline(row: FileTable) -> DocumentWithPipeline:
        """Assemble a DocumentWithPipeline from a FileTable row with joined pipeline_state."""
        document = row.to_entity()
        pipeline = row.pipeline_state.to_entity() if row.pipeline_state else PipelineState(file_id=row.file_id)
        return DocumentWithPipeline(document=document, pipeline=pipeline)

    @staticmethod
    def _base_select() -> sa.Select:
        """Base SELECT with all joined relationships."""
        return (
            sa.select(FileTable)
            .options(
                sa.orm.joinedload(FileTable.metadata_record),
                sa.orm.joinedload(FileTable.pipeline_state),
            )
        )

    # ========================================================================
    # DocumentStorePort — CRUD operations
    # ========================================================================

    async def create(self, doc: DocumentComplete) -> DocumentComplete:
        """Create a new document (files + pipeline_state + file_metadata rows)."""
        async with self._session_factory() as session:
            file_row = FileTable.from_entity(doc.document)
            pipeline_row = PipelineStateTable.from_entity(doc.pipeline)
            metadata_row = FileMetadataTable.from_entity(doc.metadata)

            file_row.pipeline_state = pipeline_row
            file_row.metadata_record = metadata_row

            session.add(file_row)
            await session.commit()
            return doc

    async def get_by_id(self, tenant_id: str, file_id: str) -> DocumentComplete | None:
        """Get a document by tenant ID and file ID."""
        async with self._session_factory() as session:
            stmt = (
                self._base_select()
                .where(FileTable.tenant_id == tenant_id, FileTable.file_id == file_id)
            )
            result = await session.execute(stmt)
            row = result.unique().scalar_one_or_none()
            if row is None:
                return None
            return self._to_document_complete(row)

    async def update(self, doc: DocumentComplete) -> DocumentComplete:
        """Update an existing document."""
        async with self._session_factory() as session:
            stmt = (
                self._base_select()
                .where(
                    FileTable.tenant_id == doc.document.tenant_id,
                    FileTable.file_id == doc.document.file_id,
                )
            )
            result = await session.execute(stmt)
            row = result.unique().scalar_one_or_none()
            if row is None:
                raise ValueError(
                    f"Document not found: tenant={doc.document.tenant_id}, file={doc.document.file_id}"
                )

            row.update_from_entity(doc.document)

            if row.pipeline_state:
                row.pipeline_state.update_from_entity(doc.pipeline)
            else:
                row.pipeline_state = PipelineStateTable.from_entity(doc.pipeline)

            if row.metadata_record:
                row.metadata_record.update_from_entity(doc.metadata)
            else:
                row.metadata_record = FileMetadataTable.from_entity(doc.metadata)

            await session.commit()
            return doc

    async def upsert(self, doc: DocumentComplete) -> DocumentComplete:
        """Create or update a document (atomic single-session)."""
        async with self._session_factory() as session:
            stmt = (
                self._base_select()
                .where(
                    FileTable.tenant_id == doc.document.tenant_id,
                    FileTable.file_id == doc.document.file_id,
                )
            )
            result = await session.execute(stmt)
            row = result.unique().scalar_one_or_none()

            if row is None:
                file_row = FileTable.from_entity(doc.document)
                file_row.pipeline_state = PipelineStateTable.from_entity(doc.pipeline)
                file_row.metadata_record = FileMetadataTable.from_entity(doc.metadata)
                session.add(file_row)
            else:
                row.update_from_entity(doc.document)
                if row.pipeline_state:
                    row.pipeline_state.update_from_entity(doc.pipeline)
                else:
                    row.pipeline_state = PipelineStateTable.from_entity(doc.pipeline)
                if row.metadata_record:
                    row.metadata_record.update_from_entity(doc.metadata)
                else:
                    row.metadata_record = FileMetadataTable.from_entity(doc.metadata)

            await session.commit()
            return doc

    async def delete(self, tenant_id: str, file_id: str) -> bool:
        """Delete a document (cascades to pipeline_state, file_metadata, chunks, events)."""
        async with self._session_factory() as session:
            stmt = sa.delete(FileTable).where(
                FileTable.tenant_id == tenant_id, FileTable.file_id == file_id
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def query_by_tenant(
        self,
        tenant_id: str,
        limit: int | None = None,
    ) -> list[DocumentComplete]:
        """Query all documents for a tenant."""
        async with self._session_factory() as session:
            stmt = (
                self._base_select()
                .where(FileTable.tenant_id == tenant_id)
                .order_by(FileTable.last_updated.desc())
            )
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return [self._to_document_complete(row) for row in result.unique().scalars().all()]

    async def count_by_tenant(self, tenant_id: str) -> int:
        """Count all documents for a tenant."""
        async with self._session_factory() as session:
            stmt = (
                sa.select(sa.func.count())
                .select_from(FileTable)
                .where(FileTable.tenant_id == tenant_id)
            )
            result = await session.execute(stmt)
            return result.scalar_one()

    async def query_by_ezshare_id(
        self,
        tenant_id: str,
        ezshare_id: str,
    ) -> DocumentComplete | None:
        """Query for a document by ezshare_id."""
        async with self._session_factory() as session:
            stmt = (
                self._base_select()
                .where(
                    FileTable.tenant_id == tenant_id,
                    FileTable.ezshare_id == ezshare_id,
                )
            )
            result = await session.execute(stmt)
            row = result.unique().scalar_one_or_none()
            if row is None:
                return None
            return self._to_document_complete(row)

    # ========================================================================
    # PipelineStorePort — processing state transitions
    # ========================================================================

    async def mark_processing(
        self,
        tenant_id: str,
        file_id: str,
        stage: ProcessingStage,
    ) -> PipelineState | None:
        """Mark a file as processing at a specific stage (atomic single-session)."""
        async with self._session_factory() as session:
            row = await self._get_pipeline_row(session, tenant_id, file_id)
            if row is None:
                return None
            entity = row.to_entity()
            entity.mark_processing(stage)
            row.update_from_entity(entity)
            await session.commit()
            return entity

    async def mark_completed(self, tenant_id: str, file_id: str) -> PipelineState | None:
        """Mark a file as completed (atomic single-session)."""
        async with self._session_factory() as session:
            row = await self._get_pipeline_row(session, tenant_id, file_id)
            if row is None:
                return None
            entity = row.to_entity()
            entity.mark_completed()
            row.update_from_entity(entity)
            await session.commit()
            return entity

    async def mark_failed(
        self,
        tenant_id: str,
        file_id: str,
        error_message: str,
    ) -> PipelineState | None:
        """Mark a file as failed with error message (atomic single-session)."""
        async with self._session_factory() as session:
            row = await self._get_pipeline_row(session, tenant_id, file_id)
            if row is None:
                return None
            entity = row.to_entity()
            entity.mark_failed(error_message)
            row.update_from_entity(entity)
            await session.commit()
            return entity

    async def update_chunk_counts(
        self,
        tenant_id: str,
        file_id: str,
        chunk_count: int,
        embedded_chunk_count: int | None = None,
    ) -> PipelineState | None:
        """Update chunk counts for a file (atomic single-session)."""
        async with self._session_factory() as session:
            row = await self._get_pipeline_row(session, tenant_id, file_id)
            if row is None:
                return None
            row.chunk_count = chunk_count
            if embedded_chunk_count is not None:
                row.embedded_chunk_count = embedded_chunk_count
            entity = row.to_entity()
            await session.commit()
            return entity

    async def update_embedded_count(
        self,
        tenant_id: str,
        file_id: str,
        embedded_count: int,
    ) -> PipelineState | None:
        """Update the embedded chunk count for a file (atomic single-session)."""
        async with self._session_factory() as session:
            row = await self._get_pipeline_row(session, tenant_id, file_id)
            if row is None:
                return None
            row.embedded_chunk_count = embedded_count
            entity = row.to_entity()
            await session.commit()
            return entity

    async def update_blob_references(
        self,
        tenant_id: str,
        file_id: str,
        raw_blob_ref: str | None = None,
        text_blob_ref: str | None = None,
    ) -> None:
        """Update blob storage references for a file (on the files table)."""
        async with self._session_factory() as session:
            stmt = (
                sa.select(FileTable)
                .where(FileTable.tenant_id == tenant_id, FileTable.file_id == file_id)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return
            if raw_blob_ref is not None:
                row.raw_blob_ref = raw_blob_ref
            if text_blob_ref is not None:
                row.text_blob_ref = text_blob_ref
            await session.commit()

    async def query_by_status(
        self,
        tenant_id: str,
        status: OverallStatus,
        limit: int | None = None,
    ) -> list[DocumentWithPipeline]:
        """Query files by processing status."""
        async with self._session_factory() as session:
            stmt = (
                sa.select(FileTable)
                .options(sa.orm.joinedload(FileTable.pipeline_state))
                .join(FileTable.pipeline_state)
                .where(
                    FileTable.tenant_id == tenant_id,
                    PipelineStateTable.overall_status == status.value,
                )
                .order_by(FileTable.last_updated.desc())
            )
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return [self._to_document_with_pipeline(row) for row in result.unique().scalars().all()]

    async def query_by_stage(
        self,
        tenant_id: str,
        stage: ProcessingStage,
        limit: int | None = None,
    ) -> list[DocumentWithPipeline]:
        """Query files by current processing stage."""
        async with self._session_factory() as session:
            stmt = (
                sa.select(FileTable)
                .options(sa.orm.joinedload(FileTable.pipeline_state))
                .join(FileTable.pipeline_state)
                .where(
                    FileTable.tenant_id == tenant_id,
                    PipelineStateTable.current_stage == stage.value,
                )
                .order_by(FileTable.last_updated.desc())
            )
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return [self._to_document_with_pipeline(row) for row in result.unique().scalars().all()]

    async def query_failed(
        self,
        tenant_id: str,
        limit: int | None = None,
    ) -> list[DocumentWithPipeline]:
        """Query all failed files for a tenant."""
        return await self.query_by_status(tenant_id, OverallStatus.FAILED, limit)

    async def query_processing(
        self,
        tenant_id: str,
        limit: int | None = None,
    ) -> list[DocumentWithPipeline]:
        """Query all currently processing files for a tenant."""
        return await self.query_by_status(tenant_id, OverallStatus.PROCESSING, limit)

    async def count_by_status(self, tenant_id: str, status: OverallStatus) -> int:
        """Count files by status."""
        async with self._session_factory() as session:
            stmt = (
                sa.select(sa.func.count())
                .select_from(FileTable)
                .join(FileTable.pipeline_state)
                .where(
                    FileTable.tenant_id == tenant_id,
                    PipelineStateTable.overall_status == status.value,
                )
            )
            result = await session.execute(stmt)
            return result.scalar_one()

    # ========================================================================
    # DocumentQueryPort — metadata-based queries
    # ========================================================================

    async def query_with_filters(
        self,
        tenant_id: str,
        filters: FileIndexFilters | None = None,
        max_results: int | None = None,
    ) -> list[DocumentComplete]:
        """Query documents with SQL WHERE filters for promoted fields."""
        async with self._session_factory() as session:
            stmt = (
                self._base_select()
                .join(FileTable.metadata_record)
                .where(FileTable.tenant_id == tenant_id)
            )

            if filters:
                stmt = self._apply_filters(stmt, filters)

            stmt = stmt.order_by(FileTable.last_updated.desc())
            stmt = stmt.limit(max_results or 100)

            result = await session.execute(stmt)
            return [self._to_document_complete(row) for row in result.unique().scalars().all()]

    @staticmethod
    def _apply_filters(stmt: sa.Select, filters: FileIndexFilters) -> sa.Select:
        """Apply FileIndexFilters as SQL WHERE clauses."""
        filter_dict = filters.model_dump(exclude_none=True)

        field_mapping = {
            "document_category": FileMetadataTable.document_category,
            "document_type": FileMetadataTable.document_type,
            "language": FileMetadataTable.language,
            "operation_number": FileMetadataTable.operation_number,
            "sector": FileMetadataTable.sector,
            "country": FileMetadataTable.country,
            "operation_type": FileMetadataTable.operation_type,
            "dept_id": FileMetadataTable.dept_id,
            "document_author": FileMetadataTable.document_author,
            "ezshare_id": FileTable.ezshare_id,
            "document_name": FileMetadataTable.document_name,
        }

        for py_field, column in field_mapping.items():
            if py_field in filter_dict:
                stmt = stmt.where(column == filter_dict[py_field])

        if "file_extension" in filter_dict:
            ext = filter_dict["file_extension"]
            if not ext.startswith("."):
                ext = f".{ext}"
            stmt = stmt.where(FileMetadataTable.file_extension == ext)

        if "disclosed" in filter_dict:
            stmt = stmt.where(FileMetadataTable.disclosed == filter_dict["disclosed"])

        if "year" in filter_dict:
            stmt = stmt.where(FileMetadataTable.year == filter_dict["year"])

        return stmt

    async def query_by_operation_number(
        self,
        tenant_id: str,
        operation_number: str,
        max_results: int | None = None,
    ) -> list[DocumentComplete]:
        """Query documents by operation number."""
        filters = FileIndexFilters(operation_number=operation_number)
        return await self.query_with_filters(tenant_id, filters, max_results)

    async def query_by_sector(
        self,
        tenant_id: str,
        sector: str,
        max_results: int | None = None,
    ) -> list[DocumentComplete]:
        """Query documents by sector classification."""
        filters = FileIndexFilters(sector=sector)
        return await self.query_with_filters(tenant_id, filters, max_results)

    async def query_by_dept_id(
        self,
        tenant_id: str,
        dept_id: str,
        max_results: int | None = None,
    ) -> list[DocumentComplete]:
        """Query documents by department ID."""
        filters = FileIndexFilters(dept_id=dept_id)
        return await self.query_with_filters(tenant_id, filters, max_results)

    async def query_disclosed_documents(
        self,
        tenant_id: str,
        disclosed: bool = True,
        max_results: int | None = None,
    ) -> list[DocumentComplete]:
        """Query documents by disclosure status."""
        filters = FileIndexFilters(disclosed=disclosed)
        return await self.query_with_filters(tenant_id, filters, max_results)

    async def count_by_sector(self, tenant_id: str, sector: str) -> int:
        """Count documents in a specific sector."""
        async with self._session_factory() as session:
            stmt = (
                sa.select(sa.func.count())
                .select_from(FileTable)
                .join(FileTable.metadata_record)
                .where(
                    FileTable.tenant_id == tenant_id,
                    FileMetadataTable.sector == sector,
                )
            )
            result = await session.execute(stmt)
            return result.scalar_one()

    async def count_by_operation_number(
        self,
        tenant_id: str,
        operation_number: str,
    ) -> int:
        """Count documents for a specific operation."""
        async with self._session_factory() as session:
            stmt = (
                sa.select(sa.func.count())
                .select_from(FileTable)
                .join(FileTable.metadata_record)
                .where(
                    FileTable.tenant_id == tenant_id,
                    FileMetadataTable.operation_number == operation_number,
                )
            )
            result = await session.execute(stmt)
            return result.scalar_one()

    # ========================================================================
    # PipelineStorePort — get_by_id returning DocumentWithPipeline
    # ========================================================================

    async def pipeline_get_by_id(
        self, tenant_id: str, file_id: str
    ) -> DocumentWithPipeline | None:
        """Get document with pipeline state by tenant ID and file ID.

        Named pipeline_get_by_id to avoid conflict with DocumentStorePort.get_by_id.
        The PipelineStorePort.get_by_id is implemented via this method.
        """
        async with self._session_factory() as session:
            stmt = (
                sa.select(FileTable)
                .options(sa.orm.joinedload(FileTable.pipeline_state))
                .where(FileTable.tenant_id == tenant_id, FileTable.file_id == file_id)
            )
            result = await session.execute(stmt)
            row = result.unique().scalar_one_or_none()
            if row is None:
                return None
            return self._to_document_with_pipeline(row)

    # ========================================================================
    # Internal helpers
    # ========================================================================

    @staticmethod
    async def _get_pipeline_row(
        session: AsyncSession, tenant_id: str, file_id: str
    ) -> PipelineStateTable | None:
        """Load a PipelineStateTable row within an existing session."""
        stmt = (
            sa.select(PipelineStateTable)
            .join(FileTable, PipelineStateTable.file_id == FileTable.file_id)
            .where(FileTable.tenant_id == tenant_id, FileTable.file_id == file_id)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
