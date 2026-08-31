"""The contract every extraction adapter must satisfy, run against every adapter there is.

This file exists so that adding an extractor is measured against the same bar as the one
already here. It knows nothing about Document Intelligence, Docling, HTML or pipe tables:
it asks only for what the canonical model promises — that blocks resolve against the text,
that cell roles are canonical, that header rows come from the cells, that a table's parts
are exactly its whole, and that any selection of its rows composes into a valid table.

Adding an adapter means adding one entry to `ADAPTERS`. If it cannot pass, either the
adapter is wrong or the contract is — and both are worth finding out before the adapter
ships rather than after a consumer depends on it.
"""

from importlib.util import find_spec
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config.settings import DocumentIntelligenceSettings
from src.core.entities.document_analysis import BlockKind, MarkdownOutput
from src.infrastructure.azure.adapters.document_intelligence_azure import (
    AzureDocumentIntelligenceAdapter,
)
from src.infrastructure.azure.adapters.document_intelligence_fake import (
    FakeDocumentIntelligenceAdapter,
)
from tests.support.document_intelligence_payloads import TABLE_PAYLOAD, analyze_result
from tests.support.extractor_contract import (
    assert_blocks_are_ordered_and_disjoint,
    assert_blocks_resolve,
    assert_every_row_subset_is_a_valid_table,
    assert_header_rows_match_the_cells,
    assert_prefix_rows_are_disjoint_from_body_rows,
    assert_rendering_is_exact,
    assert_roles_are_canonical,
    assert_rows_carry_their_provenance,
    assert_table_blocks_resolve_to_a_table,
)

pytestmark = pytest.mark.unit


async def azure_output() -> MarkdownOutput:
    """The Azure adapter over a service-shaped response whose tables are HTML."""
    client = MagicMock()
    client.analyze_document = AsyncMock(return_value=analyze_result(**TABLE_PAYLOAD))
    adapter = AzureDocumentIntelligenceAdapter(
        settings=DocumentIntelligenceSettings(
            endpoint="https://test-di.cognitiveservices.azure.com",
            api_key="test-api-key",
            use_fake=False,
        ),
        client=client,
    )
    return await adapter.analyze_document(
        document_content=b"%PDF-1.4",
        content_type="application/pdf",
        file_id="contract-azure",
    )


async def fake_output() -> MarkdownOutput:
    """The fake adapter, which renders its table as a pipe table instead."""
    adapter = FakeDocumentIntelligenceAdapter(simulated_delay_seconds=0.0)
    return await adapter.analyze_document(
        document_content=b"Report title\n\nBody paragraph.",
        content_type="text/plain",
        file_id="contract-fake",
    )


async def docling_output() -> MarkdownOutput:
    """The Docling mapper over a hand-built `DoclingDocument`.

    The mapper, not the converter: the conversion needs several hundred megabytes of model
    weights, and every promise this file checks is the mapper's. Running it against a
    document built in memory is what keeps the default `pytest` run free of artifacts while
    still holding the engine to the same bar.
    """
    from src.infrastructure.docling.mapper import map_document
    from tests.support.docling_documents import build_sample_document

    return map_document(build_sample_document(), file_id="contract-docling")


# Every adapter that exists. A new one joins this list and inherits the bar.
#
# Docling is skipped rather than failed when its optional extra is absent: an image built
# without it genuinely has no Docling adapter to hold to the contract, and pretending
# otherwise would turn a build choice into a red test.
ADAPTERS = [
    pytest.param(azure_output, id="azure-document-intelligence"),
    pytest.param(fake_output, id="fake"),
    pytest.param(
        docling_output,
        id="docling",
        marks=pytest.mark.skipif(
            find_spec("docling_core") is None,
            reason="the optional docling extra is not installed",
        ),
    ),
]

adapters = pytest.mark.parametrize("build_output", ADAPTERS)


@adapters
class TestEveryAdapterSatisfiesTheContract:
    """One class per property, so a failure names which promise an adapter broke."""

    async def test_the_output_has_blocks_at_all(self, build_output):
        """An empty block list means "structure unavailable"; an adapter must not say that."""
        output = await build_output()

        assert output.blocks, "the adapter emitted no blocks, which reads as no structure"

    async def test_every_block_resolves_against_the_extracted_text(self, build_output):
        output = await build_output()

        assert_blocks_resolve(output)
        for block in output.blocks:
            assert block.text_in(output.extracted_text)

    async def test_blocks_are_in_reading_order_and_do_not_overlap(self, build_output):
        output = await build_output()

        assert_blocks_are_ordered_and_disjoint(output)

    async def test_a_table_block_reaches_its_table(self, build_output):
        output = await build_output()

        assert any(block.kind is BlockKind.TABLE for block in output.blocks)
        assert_table_blocks_resolve_to_a_table(output)

    async def test_cell_roles_are_canonical(self, build_output):
        output = await build_output()

        for table in output.tables:
            assert_roles_are_canonical(table)

    async def test_header_rows_come_from_the_cells(self, build_output):
        output = await build_output()

        for table in output.tables:
            assert_header_rows_match_the_cells(table)

    async def test_the_parts_of_a_table_are_exactly_its_whole(self, build_output):
        """The exactness rule, for whichever form the adapter renders."""
        output = await build_output()

        assert output.tables
        for table in output.tables:
            assert_rendering_is_exact(table, output.extracted_text)

    async def test_rows_record_where_they_came_from(self, build_output):
        output = await build_output()

        for table in output.tables:
            assert_rows_carry_their_provenance(table, output.extracted_text)

    async def test_a_row_is_never_both_repeated_and_offered(self, build_output):
        output = await build_output()

        for table in output.tables:
            assert_prefix_rows_are_disjoint_from_body_rows(table)

    async def test_any_selection_of_rows_composes_into_a_valid_table(self, build_output):
        """The property that makes the rendering form a non-question for consumers."""
        output = await build_output()

        for table in output.tables:
            assert_every_row_subset_is_a_valid_table(table)

    async def test_a_consumer_composing_rows_behaves_identically_for_either_form(
        self, build_output
    ):
        """The only operation the contract asks of a consumer is concatenation.

        The same three lines run against an adapter that renders HTML and one that renders
        pipe tables, and neither needs to know which it got.
        """
        output = await build_output()
        table = output.tables[0]

        first_row_only = table.render_prefix + table.rows[0].rendered + table.render_suffix

        assert first_row_only == table.fragment(table.rows[:1])
        assert table.rows[0].rendered in first_row_only
