"""Service-shaped Document Intelligence payloads shared by the offline tests.

These build real `AnalyzeResult` models from JSON in the shape the service returns, rather
than MagicMocks: a MagicMock answers every attribute with another MagicMock, so it cannot
tell a field that is mapped from one that is silently dropped.

They live here rather than in one test module because the extractor contract test holds
every adapter to the same bar and has to reach the same document to do it.
"""

from azure.ai.documentintelligence.models import AnalyzeResult


def analyze_result(**overrides) -> AnalyzeResult:
    """Build an AnalyzeResult from a service-shaped payload."""
    payload = {"apiVersion": "2024-11-30", "modelId": "prebuilt-layout"}
    payload.update(overrides)
    return AnalyzeResult(payload)


# A document with one page and two words — the minimum the older tests asserted on.
SIMPLE_PAYLOAD = {
    "content": "# Hello World\n\nThis is extracted content.",
    "pages": [
        {
            "pageNumber": 1,
            "words": [
                {"content": "Hello", "confidence": 0.95, "span": {"offset": 2, "length": 5}},
                {"content": "World", "confidence": 0.98, "span": {"offset": 8, "length": 5}},
            ],
        }
    ],
}

# A table-bearing document, shaped like a real `prebuilt-layout` response: the markdown
# renders the table as **HTML**, the service reports a paragraph for every table cell and
# for the figure caption, and every element's span indexes into that markdown. The HTML is
# what makes the fixture worth having — a pipe table here would let a partitioner that only
# understands pipes pass while the real service was returning `<tr>`.
TABLE_HTML = (
    "<table>\n"
    '<tr>\n<th colspan="2">Budget Summary</th>\n</tr>\n'
    "<tr>\n<th>Year</th>\n<th>Amount</th>\n</tr>\n"
    "<tr>\n<td>2026</td>\n<td>1,250</td>\n</tr>\n"
    "</table>"
)
FIGURE_HTML = "<figure>\n<figcaption>Figure 1. Spend over time</figcaption>\n</figure>"
PAGE_FOOTER = '<!-- PageFooter="page 1" -->'
HEADING = "# Quarterly Report"
INTRO = "The table below summarises budgeted amounts by fiscal year."

DOCUMENT_MARKDOWN = "\n\n".join([HEADING, INTRO, TABLE_HTML, FIGURE_HTML, PAGE_FOOTER])


def span_of(text: str) -> dict:
    """The service-shaped span for a piece of the markdown.

    Offsets are looked up rather than written down so that editing the fixture cannot
    quietly leave a span pointing at the wrong characters — which is the one thing these
    tests are least able to notice. Every string passed here occurs once.
    """
    offset = DOCUMENT_MARKDOWN.index(text)
    assert DOCUMENT_MARKDOWN.count(text) == 1, f"{text!r} is not unique in the fixture"
    return {"offset": offset, "length": len(text)}


TABLE_PAYLOAD = {
    "content": DOCUMENT_MARKDOWN,
    "contentFormat": "markdown",
    "pages": [
        {
            "pageNumber": 1,
            "width": 8.5,
            "height": 11.0,
            "unit": "inch",
            "angle": 0.3,
            "spans": [{"offset": 0, "length": len(DOCUMENT_MARKDOWN)}],
            "words": [
                {"content": "Budget", "confidence": 0.99, "span": span_of("Budget")},
                {"content": "Summary", "confidence": 0.97, "span": span_of("Summary")},
            ],
            "lines": [
                {
                    "content": "Quarterly Report",
                    "spans": [span_of("Quarterly Report")],
                    "polygon": [1.0, 1.0, 7.5, 1.0, 7.5, 1.4, 1.0, 1.4],
                },
                {"content": "Budget Summary", "spans": [span_of("Budget Summary")]},
            ],
            "selectionMarks": [
                {"state": "selected", "confidence": 0.88, "spans": [{"offset": 0, "length": 1}]}
            ],
        }
    ],
    "tables": [
        {
            "rowCount": 3,
            "columnCount": 2,
            "cells": [
                {
                    "rowIndex": 0,
                    "columnIndex": 0,
                    "columnSpan": 2,
                    "kind": "columnHeader",
                    "content": "Budget Summary",
                    "elements": ["/paragraphs/2"],
                    # The cell's span covers its *content*, not the `<th>` around it —
                    # which is why rows cannot be cut at cell spans.
                    "spans": [span_of("Budget Summary")],
                    "boundingRegions": [
                        {"pageNumber": 1, "polygon": [1.0, 1.0, 7.5, 1.0, 7.5, 1.4, 1.0, 1.4]}
                    ],
                },
                {
                    "rowIndex": 1,
                    "columnIndex": 0,
                    "kind": "columnHeader",
                    "content": "Year",
                    "spans": [span_of("Year")],
                },
                {
                    "rowIndex": 1,
                    "columnIndex": 1,
                    "kind": "columnHeader",
                    "content": "Amount",
                    "spans": [span_of("Amount")],
                },
                {"rowIndex": 2, "columnIndex": 0, "content": "2026", "spans": [span_of("2026")]},
                {"rowIndex": 2, "columnIndex": 1, "content": "1,250", "spans": [span_of("1,250")]},
            ],
            "caption": {"content": "Table 1. Budget by year"},
            "footnotes": [{"content": "Amounts in thousands."}],
            "spans": [span_of(TABLE_HTML)],
            "boundingRegions": [{"pageNumber": 1, "polygon": [1.0, 1.0, 7.5, 1.0, 7.5, 3.0, 1.0, 3.0]}],
        }
    ],
    # Reading order, then the paragraphs the service also emits for each table cell and for
    # the figure caption. The block list must not repeat those: they are inside elements it
    # already reports.
    "paragraphs": [
        {
            "content": "Quarterly Report",
            "role": "title",
            "spans": [span_of(HEADING)],
            "boundingRegions": [
                {"pageNumber": 1, "polygon": [1.0, 1.0, 7.5, 1.0, 7.5, 1.4, 1.0, 1.4]}
            ],
        },
        {
            "content": INTRO,
            "spans": [span_of(INTRO)],
            "boundingRegions": [
                {"pageNumber": 1, "polygon": [1.0, 1.6, 7.5, 1.6, 7.5, 1.8, 1.0, 1.8]}
            ],
        },
        {
            "content": "page 1",
            "role": "pageFooter",
            "spans": [span_of(PAGE_FOOTER)],
            "boundingRegions": [
                {"pageNumber": 1, "polygon": [1.0, 10.2, 7.5, 10.2, 7.5, 10.4, 1.0, 10.4]}
            ],
        },
        {"content": "Budget Summary", "spans": [span_of("Budget Summary")]},
        {"content": "Year", "spans": [span_of("Year")]},
        {"content": "Amount", "spans": [span_of("Amount")]},
        {"content": "2026", "spans": [span_of("2026")]},
        {"content": "1,250", "spans": [span_of("1,250")]},
        {"content": "Figure 1. Spend over time", "spans": [span_of("Figure 1. Spend over time")]},
    ],
    "figures": [
        {
            "id": "1.1",
            "caption": {"content": "Figure 1. Spend over time"},
            "elements": ["/paragraphs/8"],
            "spans": [span_of(FIGURE_HTML)],
            "boundingRegions": [{"pageNumber": 1, "polygon": [2.0, 4.0, 6.0, 4.0, 6.0, 6.0, 2.0, 6.0]}],
        }
    ],
    "sections": [{"elements": ["/paragraphs/0", "/tables/0"]}],
    "styles": [{"isHandwritten": False, "confidence": 0.9, "fontWeight": "bold"}],
    "keyValuePairs": [
        {
            "key": {"content": "Fiscal year", "spans": [{"offset": 0, "length": 11}]},
            "value": {"content": "2026"},
            "confidence": 0.82,
        }
    ],
}
