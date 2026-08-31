"""The Docling adapter against a real conversion, with real model weights.

Everything about the *mapping* is covered offline, against a `DoclingDocument` built in
memory. What only a real conversion can prove is that the document Docling actually
produces still satisfies the canonical contract — that its labels, its provenance and its
table rendering are the ones the mapper was written against, and not the ones a fixture
author imagined.

The module is skipped unless the model artifacts are on disk. To run it:

    uv run docling-tools models download
    uv run pytest -m requires_docling_models tests/integration/infrastructure/test_docling_live.py
"""

import pytest

pytest.importorskip("docling", reason="the optional docling extra is not installed")

from src.config.settings import DoclingSettings
from src.core.entities.document_analysis import BlockKind, CoordinateUnit
from src.infrastructure.docling.adapter import DoclingExtractionAdapter
from tests.support.extractor_contract import assert_satisfies_the_extraction_contract
from tests.support.sample_documents import TABLE_ROWS, build_sample_pdf
from tests.support.table_reconstruction import assert_cells_tile_grid

pytestmark = [pytest.mark.integration, pytest.mark.requires_docling_models]


@pytest.fixture(scope="module")
def adapter() -> DoclingExtractionAdapter:
    """One adapter for the module: building it loads the models, which is the slow part."""
    return DoclingExtractionAdapter(settings=DoclingSettings())


@pytest.fixture(scope="module")
def output(adapter):
    import asyncio

    return asyncio.run(
        adapter.analyze_document(
            document_content=build_sample_pdf(),
            content_type="application/pdf",
            file_id="docling-live",
        )
    )


class TestARealConversion:
    def test_it_satisfies_the_canonical_contract(self, output):
        """The same assertions the offline adapters are held to, on a real document."""
        assert_satisfies_the_extraction_contract(output)

    def test_it_finds_the_documents_text(self, output):
        assert "Quarterly Report" in output.extracted_text
        assert "budgeted amounts by fiscal year" in output.extracted_text

    def test_it_finds_the_table_and_its_values(self, output):
        assert output.tables, "Docling reported no table on a document that has one"

        contents = {cell.content.strip() for cell in output.tables[0].cells}
        for row in TABLE_ROWS[1:]:
            for value in row:
                assert value in contents

    def test_the_table_rebuilds_from_its_cells_alone(self, output):
        for table in output.tables:
            assert_cells_tile_grid(table)

    def test_a_table_block_reaches_the_table_it_names(self, output):
        block = next(b for b in output.blocks if b.kind is BlockKind.TABLE)

        assert output.tables[block.table_index].rendered == block.text_in(
            output.extracted_text
        )

    def test_geometry_arrives_in_doclings_own_unit(self, output):
        boxed = [b for b in output.blocks if b.bounding_box is not None]

        assert boxed, "no block carried geometry"
        assert all(b.bounding_box.unit is CoordinateUnit.POINT for b in boxed)

    def test_it_records_the_engine_and_carries_the_raw_document(self, output):
        metadata = output.extraction_metadata

        assert metadata.extraction_method == "docling"
        assert metadata.analysis_format == "docling-document"
        assert output.raw_analysis["schema_name"] == "DoclingDocument"
        assert metadata.page_count == 1
