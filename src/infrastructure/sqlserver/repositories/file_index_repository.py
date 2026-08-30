"""SQL Server repository for FileIndex entities."""

import logging

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.dto.file_index_filters import FileIndexFilters
from src.core.entities.file_index import FileIndex, OverallStatus, ProcessingStage
from src.infrastructure.sqlserver.models.file_metadata_model import FileMetadataTable
from src.infrastructure.sqlserver.models.file_model import FileTable
from src.infrastructure.sqlserver.models.pipeline_state_model import PipelineStateTable

logger = logging.getLogger(__name__)


class FileIndexRepositorySQLServer:
    """Repository for managing FileIndex entities in SQL Server.

    Backed by the `files` + `file_metadata` tables in SQL Server.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def close(self) -> None:
        """No-op: session lifecycle is managed per-request."""
        pass

    @staticmethod
    def _base_select() -> sa.Select:
        """SELECT with all joined relationships needed to assemble a FileIndex."""
        return (
            sa.select(FileTable)
            .options(
                sa.orm.joinedload(FileTable.pipeline_state),
                sa.orm.joinedload(FileTable.metadata_record),
            )
        )

    async def create(self, file_index: FileIndex) -> FileIndex:
        """Create a new FileIndex entity (files + pipeline_state + file_metadata rows)."""
        async with self._session_factory() as session:
            file_row = FileTable.from_file_index(file_index)
            file_row.pipeline_state = PipelineStateTable.from_file_index(file_index)
            file_row.metadata_record = FileMetadataTable.from_file_index(file_index)

            session.add(file_row)
            await session.commit()
            return file_index

    async def get_by_id(self, tenant_id: str, file_id: str) -> FileIndex | None:
        """Get a FileIndex by tenant ID and file ID."""
        async with self._session_factory() as session:
            stmt = self._base_select().where(
                FileTable.tenant_id == tenant_id, FileTable.file_id == file_id
            )
            result = await session.execute(stmt)
            row = result.unique().scalar_one_or_none()
            if row is None:
                return None
            return row.to_file_index()

    async def update(self, file_index: FileIndex) -> FileIndex:
        """Update an existing FileIndex entity."""
        async with self._session_factory() as session:
            stmt = self._base_select().where(
                FileTable.tenant_id == file_index.tenant_id,
                FileTable.file_id == file_index.file_id,
            )
            result = await session.execute(stmt)
            row = result.unique().scalar_one_or_none()
            if row is None:
                raise ValueError(
                    f"FileIndex not found: tenant={file_index.tenant_id}, file={file_index.file_id}"
                )

            row.update_from_file_index(file_index)

            if row.pipeline_state:
                row.pipeline_state.update_from_file_index(file_index)
            else:
                row.pipeline_state = PipelineStateTable.from_file_index(file_index)

            if row.metadata_record:
                row.metadata_record.update_from_file_index(file_index)
            else:
                row.metadata_record = FileMetadataTable.from_file_index(file_index)

            await session.commit()
            return file_index

    async def upsert(self, file_index: FileIndex) -> FileIndex:
        """Create or update a FileIndex entity (atomic single-session)."""
        async with self._session_factory() as session:
            stmt = self._base_select().where(
                FileTable.tenant_id == file_index.tenant_id,
                FileTable.file_id == file_index.file_id,
            )
            result = await session.execute(stmt)
            row = result.unique().scalar_one_or_none()

            if row is None:
                file_row = FileTable.from_file_index(file_index)
                file_row.pipeline_state = PipelineStateTable.from_file_index(file_index)
                file_row.metadata_record = FileMetadataTable.from_file_index(file_index)
                session.add(file_row)
            else:
                row.update_from_file_index(file_index)
                if row.pipeline_state:
                    row.pipeline_state.update_from_file_index(file_index)
                else:
                    row.pipeline_state = PipelineStateTable.from_file_index(file_index)
                if row.metadata_record:
                    row.metadata_record.update_from_file_index(file_index)
                else:
                    row.metadata_record = FileMetadataTable.from_file_index(file_index)

            await session.commit()
            return file_index

    async def delete(self, tenant_id: str, file_id: str) -> bool:
        """Delete a FileIndex entity (cascades to file_metadata, chunks, events)."""
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
    ) -> list[FileIndex]:
        """Query all files for a tenant."""
        async with self._session_factory() as session:
            stmt = (
                self._base_select()
                .where(FileTable.tenant_id == tenant_id)
                .order_by(FileTable.last_updated.desc())
            )
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return [row.to_file_index() for row in result.unique().scalars().all()]

    async def query_by_status(
        self,
        tenant_id: str,
        status: OverallStatus,
        limit: int | None = None,
    ) -> list[FileIndex]:
        """Query files by processing status."""
        async with self._session_factory() as session:
            stmt = (
                self._base_select()
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
            return [row.to_file_index() for row in result.unique().scalars().all()]

    async def query_by_stage(
        self,
        tenant_id: str,
        stage: ProcessingStage,
        limit: int | None = None,
    ) -> list[FileIndex]:
        """Query files by current processing stage."""
        async with self._session_factory() as session:
            stmt = (
                self._base_select()
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
            return [row.to_file_index() for row in result.unique().scalars().all()]

    async def query_failed(
        self,
        tenant_id: str,
        limit: int | None = None,
    ) -> list[FileIndex]:
        """Query all failed files for a tenant."""
        return await self.query_by_status(tenant_id, OverallStatus.FAILED, limit)

    async def query_processing(
        self,
        tenant_id: str,
        limit: int | None = None,
    ) -> list[FileIndex]:
        """Query all currently processing files for a tenant."""
        return await self.query_by_status(tenant_id, OverallStatus.PROCESSING, limit)

    async def mark_processing(
        self,
        tenant_id: str,
        file_id: str,
        stage: ProcessingStage,
    ) -> FileIndex | None:
        """Mark a file as processing at a specific stage (atomic single-session)."""
        async with self._session_factory() as session:
            row = await self._get_file_row(session, tenant_id, file_id)
            if row is None:
                return None
            entity = row.to_file_index()
            entity.mark_processing(stage)
            if row.pipeline_state:
                row.pipeline_state.update_from_file_index(entity)
            await session.commit()
            return entity

    async def mark_completed(self, tenant_id: str, file_id: str) -> FileIndex | None:
        """Mark a file as completed (atomic single-session)."""
        async with self._session_factory() as session:
            row = await self._get_file_row(session, tenant_id, file_id)
            if row is None:
                return None
            entity = row.to_file_index()
            entity.mark_completed()
            if row.pipeline_state:
                row.pipeline_state.update_from_file_index(entity)
            await session.commit()
            return entity

    async def mark_failed(
        self,
        tenant_id: str,
        file_id: str,
        error_message: str,
    ) -> FileIndex | None:
        """Mark a file as failed with error message (atomic single-session)."""
        async with self._session_factory() as session:
            row = await self._get_file_row(session, tenant_id, file_id)
            if row is None:
                return None
            entity = row.to_file_index()
            entity.mark_failed(error_message)
            if row.pipeline_state:
                row.pipeline_state.update_from_file_index(entity)
            await session.commit()
            return entity

    async def update_chunk_counts(
        self,
        tenant_id: str,
        file_id: str,
        chunk_count: int,
        embedded_chunk_count: int | None = None,
    ) -> FileIndex | None:
        """Update chunk counts for a file (atomic single-session)."""
        async with self._session_factory() as session:
            row = await self._get_file_row(session, tenant_id, file_id)
            if row is None:
                return None
            if row.pipeline_state:
                row.pipeline_state.chunk_count = chunk_count
                if embedded_chunk_count is not None:
                    row.pipeline_state.embedded_chunk_count = embedded_chunk_count
            await session.commit()
            return row.to_file_index()

    async def update_embedded_count(
        self,
        tenant_id: str,
        file_id: str,
        embedded_count: int,
    ) -> FileIndex | None:
        """Update the embedded chunk count for a file (atomic single-session)."""
        async with self._session_factory() as session:
            row = await self._get_file_row(session, tenant_id, file_id)
            if row is None:
                return None
            if row.pipeline_state:
                row.pipeline_state.embedded_chunk_count = embedded_count
            await session.commit()
            return row.to_file_index()

    async def update_blob_references(
        self,
        tenant_id: str,
        file_id: str,
        raw_blob_ref: str | None = None,
        text_blob_ref: str | None = None,
        analysis_blob_ref: str | None = None,
        clear_analysis_blob_ref: bool = False,
    ) -> FileIndex | None:
        """Update blob storage references for a file (atomic single-session)."""
        async with self._session_factory() as session:
            row = await self._get_file_row(session, tenant_id, file_id)
            if row is None:
                return None
            if raw_blob_ref is not None:
                row.raw_blob_ref = raw_blob_ref
            if text_blob_ref is not None:
                row.text_blob_ref = text_blob_ref
            if analysis_blob_ref is not None:
                row.analysis_blob_ref = analysis_blob_ref
            elif clear_analysis_blob_ref:
                # A re-run that stored no sidecar must not leave the row pointing at the
                # previous run's analysis.json, which no longer describes this text.json.
                row.analysis_blob_ref = None
            await session.commit()
            return row.to_file_index()

    async def count_by_tenant(self, tenant_id: str) -> int:
        """Count all files for a tenant."""
        async with self._session_factory() as session:
            stmt = (
                sa.select(sa.func.count())
                .select_from(FileTable)
                .where(FileTable.tenant_id == tenant_id)
            )
            result = await session.execute(stmt)
            return result.scalar_one()

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

    async def query_with_filters(
        self,
        tenant_id: str,
        filters: FileIndexFilters | None = None,
        max_results: int | None = None,
    ) -> list[FileIndex]:
        """Query FileIndex with SQL WHERE filters for promoted fields."""
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
            return [row.to_file_index() for row in result.unique().scalars().all()]

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
    ) -> list[FileIndex]:
        """Query documents by operation number."""
        filters = FileIndexFilters(operation_number=operation_number)
        return await self.query_with_filters(tenant_id, filters, max_results)

    async def query_by_sector(
        self,
        tenant_id: str,
        sector: str,
        max_results: int | None = None,
    ) -> list[FileIndex]:
        """Query documents by sector classification."""
        filters = FileIndexFilters(sector=sector)
        return await self.query_with_filters(tenant_id, filters, max_results)

    async def query_by_dept_id(
        self,
        tenant_id: str,
        dept_id: str,
        max_results: int | None = None,
    ) -> list[FileIndex]:
        """Query documents by department ID."""
        filters = FileIndexFilters(dept_id=dept_id)
        return await self.query_with_filters(tenant_id, filters, max_results)

    async def query_disclosed_documents(
        self,
        tenant_id: str,
        disclosed: bool = True,
        max_results: int | None = None,
    ) -> list[FileIndex]:
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

    async def query_by_ezshare_id(
        self,
        tenant_id: str,
        ezshare_id: str,
    ) -> FileIndex | None:
        """Query for a file by ezshare_id."""
        async with self._session_factory() as session:
            stmt = self._base_select().where(
                FileTable.tenant_id == tenant_id,
                FileTable.ezshare_id == ezshare_id,
            )
            result = await session.execute(stmt)
            row = result.unique().scalar_one_or_none()
            if row is None:
                return None
            return row.to_file_index()

    @staticmethod
    async def _get_file_row(
        session: AsyncSession, tenant_id: str, file_id: str
    ) -> FileTable | None:
        """Load a FileTable row with pipeline_state and metadata within an existing session."""
        stmt = (
            sa.select(FileTable)
            .options(
                sa.orm.joinedload(FileTable.pipeline_state),
                sa.orm.joinedload(FileTable.metadata_record),
            )
            .where(FileTable.tenant_id == tenant_id, FileTable.file_id == file_id)
        )
        result = await session.execute(stmt)
        return result.unique().scalar_one_or_none()
