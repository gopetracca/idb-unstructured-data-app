"""Blob-reference updates against a real SQL Server, including the raw-analysis column.

These run the repository against the schema Alembic actually produces — `files` is a
system-versioned temporal table, so migration 011's add-column dance is exercised here
too, not just reviewed.

Requires Docker: the session-scoped `sqlserver_container` fixture starts SQL Server 2022,
creates the test database, and runs `alembic upgrade head` before yielding.
"""

import asyncio
import uuid

import pytest

from src.core.entities.composites import DocumentComplete
from src.core.entities.document import Document
from src.core.entities.pipeline_state import OverallStatus, PipelineState, ProcessingStage
from src.core.value_objects.document_metadata import DocumentMetadata
from src.infrastructure.sqlserver.repositories.document_repository import (
    DocumentRepositorySQLServer,
)

pytestmark = [pytest.mark.integration, pytest.mark.requires_sqlserver]

TENANT = "analysis-ref-tests"


@pytest.fixture
def repository(sqlserver_session_factory) -> DocumentRepositorySQLServer:
    return DocumentRepositorySQLServer(session_factory=sqlserver_session_factory)


@pytest.fixture
async def stored_document(repository: DocumentRepositorySQLServer) -> DocumentComplete:
    """Insert a fresh document and clean it up afterwards."""
    file_id = str(uuid.uuid4())
    doc = DocumentComplete(
        document=Document(
            tenant_id=TENANT,
            file_id=file_id,
            blob_name="report.pdf",
            content_type="application/pdf",
            size_bytes=2048,
            content_hash="hash-" + file_id[:8],
            raw_blob_ref=f"{TENANT}/{file_id}/report.pdf",
        ),
        pipeline=PipelineState(
            tenant_id=TENANT,
            file_id=file_id,
            current_stage=ProcessingStage.CONVERT,
            overall_status=OverallStatus.PROCESSING,
        ),
        metadata=DocumentMetadata(tenant_id=TENANT, file_id=file_id),
    )
    await repository.create(doc)
    yield doc
    await repository.delete(TENANT, file_id)


async def _analysis_ref(repository: DocumentRepositorySQLServer, file_id: str) -> str | None:
    stored = await repository.get_by_id(TENANT, file_id)
    return stored.document.analysis_blob_ref


class TestAnalysisBlobRefRoundTrip:
    """The column added by migration 011 behaves as the schema claims."""

    async def test_column_exists_and_defaults_to_null(
        self, repository: DocumentRepositorySQLServer, stored_document: DocumentComplete
    ):
        """Rows predating the sidecar have no raw analysis, and that must be legal."""
        assert await _analysis_ref(repository, stored_document.document.file_id) is None

    async def test_reference_is_persisted(
        self, repository: DocumentRepositorySQLServer, stored_document: DocumentComplete
    ):
        file_id = stored_document.document.file_id
        path = f"{TENANT}/{file_id}/analysis.json"

        await repository.update_blob_references(
            tenant_id=TENANT,
            file_id=file_id,
            text_blob_ref=f"{TENANT}/{file_id}/text.json",
            analysis_blob_ref=path,
        )

        assert await _analysis_ref(repository, file_id) == path


class TestAnalysisBlobRefIsNotLeftStale:
    """A re-run that stores no sidecar must not inherit the previous run's path.

    `None` means "leave it alone" for every reference, which is what stops one stage from
    wiping another's path. That default is wrong for a re-processed document: SQL would
    keep pointing at an analysis.json describing the *earlier* run while the text.json
    just written says `raw_analysis_stored: false`. Hence the explicit clear.
    """

    async def test_none_alone_does_not_clear(
        self, repository: DocumentRepositorySQLServer, stored_document: DocumentComplete
    ):
        """The 'leave it alone' default is intact — other callers depend on it."""
        file_id = stored_document.document.file_id
        path = f"{TENANT}/{file_id}/analysis.json"
        await repository.update_blob_references(
            tenant_id=TENANT, file_id=file_id, analysis_blob_ref=path
        )

        await repository.update_blob_references(
            tenant_id=TENANT, file_id=file_id, text_blob_ref=f"{TENANT}/{file_id}/text.json"
        )

        assert await _analysis_ref(repository, file_id) == path

    async def test_explicit_clear_nulls_the_reference(
        self, repository: DocumentRepositorySQLServer, stored_document: DocumentComplete
    ):
        file_id = stored_document.document.file_id
        await repository.update_blob_references(
            tenant_id=TENANT,
            file_id=file_id,
            analysis_blob_ref=f"{TENANT}/{file_id}/analysis.json",
        )

        await repository.update_blob_references(
            tenant_id=TENANT,
            file_id=file_id,
            text_blob_ref=f"{TENANT}/{file_id}/text.json",
            clear_analysis_blob_ref=True,
        )

        assert await _analysis_ref(repository, file_id) is None

    async def test_a_supplied_path_wins_over_the_clear_flag(
        self, repository: DocumentRepositorySQLServer, stored_document: DocumentComplete
    ):
        """Belt and braces: a caller passing both must still get the write."""
        file_id = stored_document.document.file_id
        path = f"{TENANT}/{file_id}/analysis.json"

        await repository.update_blob_references(
            tenant_id=TENANT,
            file_id=file_id,
            analysis_blob_ref=path,
            clear_analysis_blob_ref=True,
        )

        assert await _analysis_ref(repository, file_id) == path

    async def test_clearing_leaves_the_other_references_alone(
        self, repository: DocumentRepositorySQLServer, stored_document: DocumentComplete
    ):
        file_id = stored_document.document.file_id
        text_path = f"{TENANT}/{file_id}/text.json"

        await repository.update_blob_references(
            tenant_id=TENANT,
            file_id=file_id,
            text_blob_ref=text_path,
            clear_analysis_blob_ref=True,
        )

        stored = await repository.get_by_id(TENANT, file_id)
        assert stored.document.analysis_blob_ref is None
        assert stored.document.text_blob_ref == text_path
        assert stored.document.raw_blob_ref == f"{TENANT}/{file_id}/report.pdf"


class TestTheUpdateReportsWhatItDisplaced:
    """Cleanup depends on this being the row's state at write time, not at read time."""

    async def test_first_write_displaces_nothing(
        self, repository: DocumentRepositorySQLServer, stored_document: DocumentComplete
    ):
        file_id = stored_document.document.file_id

        replaced = await repository.update_blob_references(
            tenant_id=TENANT,
            file_id=file_id,
            text_blob_ref=f"{TENANT}/{file_id}/text/run-1.json",
            analysis_blob_ref=f"{TENANT}/{file_id}/analysis/run-1.json",
        )

        assert replaced.text_blob_ref is None
        assert replaced.analysis_blob_ref is None

    async def test_a_later_write_reports_the_pair_it_replaced(
        self, repository: DocumentRepositorySQLServer, stored_document: DocumentComplete
    ):
        file_id = stored_document.document.file_id
        first = (
            f"{TENANT}/{file_id}/text/run-1.json",
            f"{TENANT}/{file_id}/analysis/run-1.json",
        )
        await repository.update_blob_references(
            tenant_id=TENANT,
            file_id=file_id,
            text_blob_ref=first[0],
            analysis_blob_ref=first[1],
        )

        replaced = await repository.update_blob_references(
            tenant_id=TENANT,
            file_id=file_id,
            text_blob_ref=f"{TENANT}/{file_id}/text/run-2.json",
            analysis_blob_ref=f"{TENANT}/{file_id}/analysis/run-2.json",
        )

        assert (replaced.text_blob_ref, replaced.analysis_blob_ref) == first
        stored = await repository.get_by_id(TENANT, file_id)
        assert stored.document.text_blob_ref.endswith("run-2.json")

    async def test_clearing_reports_the_analysis_it_removed(
        self, repository: DocumentRepositorySQLServer, stored_document: DocumentComplete
    ):
        file_id = stored_document.document.file_id
        analysis = f"{TENANT}/{file_id}/analysis/run-1.json"
        await repository.update_blob_references(
            tenant_id=TENANT, file_id=file_id, analysis_blob_ref=analysis
        )

        replaced = await repository.update_blob_references(
            tenant_id=TENANT,
            file_id=file_id,
            text_blob_ref=f"{TENANT}/{file_id}/text/run-2.json",
            clear_analysis_blob_ref=True,
        )

        assert replaced.analysis_blob_ref == analysis
        stored = await repository.get_by_id(TENANT, file_id)
        assert stored.document.analysis_blob_ref is None

    async def test_an_unknown_document_displaces_nothing(
        self, repository: DocumentRepositorySQLServer
    ):
        replaced = await repository.update_blob_references(
            tenant_id=TENANT, file_id="does-not-exist", text_blob_ref="x"
        )

        assert replaced.text_blob_ref is None
        assert replaced.analysis_blob_ref is None


class TestTwoSessionsPublishingConcurrently:
    """Two publishes racing over the same row, each in its own session.

    This is the case the in-process tests cannot prove. Cleanup is driven by what each
    publish reports as displaced, so if two concurrent statements can both report the same
    previous pair, the outputs of whichever committed first are orphaned with nothing left
    to delete them. Only a real database can settle whether that is possible.
    """

    async def test_each_publish_reports_a_different_predecessor(
        self, repository: DocumentRepositorySQLServer, stored_document: DocumentComplete
    ):
        file_id = stored_document.document.file_id
        original = (
            f"{TENANT}/{file_id}/text/seed.json",
            f"{TENANT}/{file_id}/analysis/seed.json",
        )
        await repository.update_blob_references(
            tenant_id=TENANT,
            file_id=file_id,
            text_blob_ref=original[0],
            analysis_blob_ref=original[1],
        )

        async def publish(run: str):
            return await repository.update_blob_references(
                tenant_id=TENANT,
                file_id=file_id,
                text_blob_ref=f"{TENANT}/{file_id}/text/{run}.json",
                analysis_blob_ref=f"{TENANT}/{file_id}/analysis/{run}.json",
            )

        first, second = await asyncio.gather(publish("run-a"), publish("run-b"))

        reported = [
            (first.text_blob_ref, first.analysis_blob_ref),
            (second.text_blob_ref, second.analysis_blob_ref),
        ]

        # One publish displaced the original pair; the other displaced whatever that one
        # published. If both reported the original, one run's outputs would leak.
        assert original in reported
        assert reported[0] != reported[1], (
            "both concurrent publishes reported the same predecessor, so the outputs of "
            "the run that committed first would never be cleaned up"
        )

        # And every published pair is accounted for: the row holds one of them, the other
        # was reported as displaced and would be swept by its publisher.
        stored = await repository.get_by_id(TENANT, file_id)
        published = (stored.document.text_blob_ref, stored.document.analysis_blob_ref)
        assert published not in reported
        assert {published, original} | {tuple(r) for r in reported} == {
            published,
            original,
            *[tuple(r) for r in reported],
        }

    async def test_many_concurrent_publishes_form_a_chain(
        self, repository: DocumentRepositorySQLServer, stored_document: DocumentComplete
    ):
        """Every pair except the surviving one is reported displaced exactly once.

        That is the property cleanup depends on: each output is deleted by exactly one
        publisher, and the published pair is deleted by none.
        """
        file_id = stored_document.document.file_id
        # Named distinctly from the concurrent runs: if a run reused these paths, two
        # publishes would displace identical values and the uniqueness check below would
        # fail for a reason that has nothing to do with concurrency.
        original = (
            f"{TENANT}/{file_id}/text/seed.json",
            f"{TENANT}/{file_id}/analysis/seed.json",
        )
        await repository.update_blob_references(
            tenant_id=TENANT,
            file_id=file_id,
            text_blob_ref=original[0],
            analysis_blob_ref=original[1],
        )

        runs = [f"run-{i}" for i in range(8)]

        async def publish(run: str):
            replaced = await repository.update_blob_references(
                tenant_id=TENANT,
                file_id=file_id,
                text_blob_ref=f"{TENANT}/{file_id}/text/{run}.json",
                analysis_blob_ref=f"{TENANT}/{file_id}/analysis/{run}.json",
            )
            return (replaced.text_blob_ref, replaced.analysis_blob_ref)

        displaced = await asyncio.gather(*(publish(run) for run in runs))

        # No pair is displaced twice — otherwise two publishers would delete the same
        # outputs and some other pair would never be deleted at all.
        assert len(set(displaced)) == len(displaced)

        stored = await repository.get_by_id(TENANT, file_id)
        published = (stored.document.text_blob_ref, stored.document.analysis_blob_ref)

        written = {original} | {
            (f"{TENANT}/{file_id}/text/{run}.json", f"{TENANT}/{file_id}/analysis/{run}.json")
            for run in runs
        }
        # Everything written was either displaced by exactly one publisher, or is the pair
        # the row now points at.
        assert set(displaced) | {published} == written
        assert published not in set(displaced)
