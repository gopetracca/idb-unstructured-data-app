"""Sample documents built on the fly for tests that need a real file to analyse.

Generated rather than committed as binaries so the expected structure is visible next to
the assertions that depend on it, and so a failure can be read against the source.
"""

import io

# The table `build_sample_pdf` draws. Row 0 is a title merged across both columns, row 1
# is a column-header row, rows 2-3 are data. Merged cells and header rows are the two
# things a rendered-markdown-only representation cannot round-trip, which is why the
# sample has both.
TABLE_ROWS: list[list[str]] = [
    ["Budget Summary", ""],
    ["Year", "Amount"],
    ["2025", "980"],
    ["2026", "1250"],
]

HEADING = "Quarterly Report"
BODY = "The table below summarises budgeted amounts by fiscal year."


def build_sample_pdf() -> bytes:
    """Draw a one-page PDF with a heading, a paragraph, and a merged-cell table."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()

    table = Table(TABLE_ROWS)
    table.setStyle(
        TableStyle(
            [
                # Merge the title cell across both columns of row 0.
                ("SPAN", (0, 0), (1, 0)),
                ("GRID", (0, 0), (-1, -1), 0.75, (0, 0, 0)),
                ("BACKGROUND", (0, 0), (-1, 1), (0.85, 0.85, 0.85)),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )

    doc.build(
        [
            Paragraph(HEADING, styles["Title"]),
            Paragraph(BODY, styles["BodyText"]),
            Spacer(1, 18),
            table,
        ]
    )
    return buffer.getvalue()
