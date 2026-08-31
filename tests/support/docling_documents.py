"""`DoclingDocument` fixtures built by hand, so the mapper can be tested without models.

Docling's converter needs several hundred megabytes of model weights and seconds of CPU
per document; its *document model* needs neither. Building the document directly is what
lets the mapper — where every mapping decision lives — be tested in milliseconds, and
leaves the converter itself to the marked test that needs real artifacts.

The table here has the two features a rendered-markdown-only representation cannot
round-trip: a cell merged across a row, and a header that is not merely "the first row".
"""

from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.document import (
    DoclingDocument,
    ProvenanceItem,
    TableData,
)
from docling_core.types.doc.document import TableCell as DoclingTableCell

PAGE_WIDTH = 612.0
PAGE_HEIGHT = 792.0

TITLE = "Quarterly Report"
BODY = "The table below summarises budgeted amounts by fiscal year."
CAPTION = "Budgeted amounts, 2025-2026."


def _prov(page_no: int, top: float, bottom: float) -> ProvenanceItem:
    """A provenance entry in Docling's own convention: points, measured bottom-left.

    `t` above `b` is not a mistake — with a bottom-left origin the larger number is the
    higher edge, which is exactly the convention difference the canonical model records
    rather than converts away.
    """
    return ProvenanceItem(
        page_no=page_no,
        bbox=BoundingBox(
            l=72.0, t=top, r=540.0, b=bottom, coord_origin=CoordOrigin.BOTTOMLEFT
        ),
        charspan=(0, 0),
    )


def budget_table_data() -> TableData:
    """A 4x2 table whose first two rows are headers and whose first cell spans both columns."""
    cells = [
        DoclingTableCell(
            text="Budget Summary",
            start_row_offset_idx=0,
            end_row_offset_idx=1,
            start_col_offset_idx=0,
            end_col_offset_idx=2,
            row_span=1,
            col_span=2,
            column_header=True,
        ),
        DoclingTableCell(
            text="Year",
            start_row_offset_idx=1,
            end_row_offset_idx=2,
            start_col_offset_idx=0,
            end_col_offset_idx=1,
            column_header=True,
        ),
        DoclingTableCell(
            text="Amount",
            start_row_offset_idx=1,
            end_row_offset_idx=2,
            start_col_offset_idx=1,
            end_col_offset_idx=2,
            column_header=True,
        ),
        DoclingTableCell(
            text="2025",
            start_row_offset_idx=2,
            end_row_offset_idx=3,
            start_col_offset_idx=0,
            end_col_offset_idx=1,
        ),
        DoclingTableCell(
            text="980",
            start_row_offset_idx=2,
            end_row_offset_idx=3,
            start_col_offset_idx=1,
            end_col_offset_idx=2,
        ),
        DoclingTableCell(
            text="2026",
            start_row_offset_idx=3,
            end_row_offset_idx=4,
            start_col_offset_idx=0,
            end_col_offset_idx=1,
        ),
        DoclingTableCell(
            text="1250",
            start_row_offset_idx=3,
            end_row_offset_idx=4,
            start_col_offset_idx=1,
            end_col_offset_idx=2,
        ),
    ]
    return TableData(num_rows=4, num_cols=2, table_cells=cells)


def build_sample_document() -> DoclingDocument:
    """A one-page document with a title, a paragraph, a captioned table, and a picture."""
    doc = DoclingDocument(name="sample")
    doc.add_page(page_no=1, size=Size(width=PAGE_WIDTH, height=PAGE_HEIGHT))

    doc.add_title(text=TITLE, prov=_prov(1, 720.0, 700.0))
    doc.add_text(label="text", text=BODY, prov=_prov(1, 690.0, 670.0))

    caption = doc.add_text(label="caption", text=CAPTION, prov=_prov(1, 660.0, 650.0))
    doc.add_table(data=budget_table_data(), caption=caption, prov=_prov(1, 640.0, 560.0))
    doc.add_picture(prov=_prov(1, 550.0, 450.0))

    return doc


def build_table_with_a_vertical_merge() -> DoclingDocument:
    """A table whose first column merges two rows, so one row continues from another.

    A fragment holding only the second row would silently lose the merged cell's content,
    which is the case `TableRow.continues_from_row` exists to make visible.
    """
    doc = DoclingDocument(name="merged")
    doc.add_page(page_no=1, size=Size(width=PAGE_WIDTH, height=PAGE_HEIGHT))
    cells = [
        DoclingTableCell(
            text="Region",
            start_row_offset_idx=0,
            end_row_offset_idx=1,
            start_col_offset_idx=0,
            end_col_offset_idx=1,
            column_header=True,
        ),
        DoclingTableCell(
            text="Amount",
            start_row_offset_idx=0,
            end_row_offset_idx=1,
            start_col_offset_idx=1,
            end_col_offset_idx=2,
            column_header=True,
        ),
        DoclingTableCell(
            text="Andean",
            start_row_offset_idx=1,
            end_row_offset_idx=3,
            start_col_offset_idx=0,
            end_col_offset_idx=1,
            row_span=2,
        ),
        DoclingTableCell(
            text="980",
            start_row_offset_idx=1,
            end_row_offset_idx=2,
            start_col_offset_idx=1,
            end_col_offset_idx=2,
        ),
        DoclingTableCell(
            text="1250",
            start_row_offset_idx=2,
            end_row_offset_idx=3,
            start_col_offset_idx=1,
            end_col_offset_idx=2,
        ),
    ]
    doc.add_table(
        data=TableData(num_rows=3, num_cols=2, table_cells=cells),
        prov=_prov(1, 640.0, 560.0),
    )
    return doc
