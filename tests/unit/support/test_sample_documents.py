"""The live tests' sample document is built by code, so the builder is worth a test.

Without this, a broken sample PDF would only show up as a confusing failure on a machine
that has Azure credentials — which is the machine least able to tell a builder bug from a
service change.
"""

import pytest

from tests.support.sample_documents import BODY, HEADING, TABLE_ROWS, build_sample_pdf

pytestmark = pytest.mark.unit


def test_sample_pdf_is_a_pdf():
    content = build_sample_pdf()

    assert content.startswith(b"%PDF-")
    assert len(content) > 500


def test_sample_table_has_a_merged_title_and_a_header_row():
    """The two shapes the live assertions depend on."""
    assert TABLE_ROWS[0][1] == "", "row 0 must be the merged title, so its second cell is empty"
    assert TABLE_ROWS[1] == ["Year", "Amount"]
    assert len(TABLE_ROWS) == 4
    assert all(len(row) == 2 for row in TABLE_ROWS)


def test_sample_text_is_present_for_the_extraction_assertions():
    assert HEADING and BODY
    assert HEADING not in BODY
