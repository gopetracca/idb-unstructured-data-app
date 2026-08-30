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


def build_sample_image() -> bytes:
    """Draw the same document as a PNG, so the image path can be analysed too.

    Document Intelligence measures an image page in **pixels** and a PDF page in inches.
    That difference is invisible in the coordinates themselves — both are small positive
    floats — so the only way to find an adapter labelling one as the other is to analyse
    both. Hence a second sample rather than a second assertion on the first.
    """
    from PIL import Image, ImageDraw

    width, height = 1275, 1650  # US Letter at 150 dpi
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    draw.text((110, 90), HEADING, fill="black")
    draw.text((110, 150), BODY, fill="black")

    # A grid with one row of text per line, so the service reads a table rather than a
    # block of prose. Drawn large enough that OCR is not the thing under test.
    top, row_height, left = 260, 70, 110
    column_width = 420
    for index, row in enumerate(TABLE_ROWS):
        y = top + index * row_height
        draw.rectangle([left, y, left + 2 * column_width, y + row_height], outline="black")
        if index == 0:
            # The merged title cell spans both columns, as it does in the PDF.
            draw.text((left + 20, y + 25), row[0], fill="black")
            continue
        draw.line([left + column_width, y, left + column_width, y + row_height], fill="black")
        for column, cell in enumerate(row):
            draw.text((left + column * column_width + 20, y + 25), cell, fill="black")

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
