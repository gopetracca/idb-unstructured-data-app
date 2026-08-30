"""Document analysis entities and value objects for Document Intelligence processing.

These value objects mirror the structural elements Document Intelligence returns for a
document — tables, figures, paragraphs, sections, styles, key-value pairs, and per-page
lines, words and selection marks — so that nothing the service found is lost between the
`convert` stage and the consumers downstream of it.

Two properties are deliberate and load-bearing:

- **Spans are preserved on every element that has one.** A span is an ``(offset, length)``
  pair into :attr:`MarkdownOutput.extracted_text`, which makes it possible to map any
  element back onto the markdown a chunk was cut from.
- **The model is additive.** ``extracted_text``, ``pages[].text``, ``pages[].word_count``
  and the original ``ExtractionMetadata`` fields keep their meaning, so a ``text.json``
  written before structural preservation existed still deserialises, and consumers that
  only read ``extracted_text`` (the chunker) are unaffected.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TextSpan(BaseModel):
    """A region of :attr:`MarkdownOutput.extracted_text` an element came from."""

    offset: int = Field(default=0, ge=0, description="Start index into the extracted text")
    length: int = Field(default=0, ge=0, description="Length of the region in characters")


class BoundingRegion(BaseModel):
    """Where an element sits on a page."""

    page_number: int = Field(..., ge=1, description="1-indexed page the region is on")
    polygon: list[float] = Field(
        default_factory=list,
        description="Flattened x,y pairs bounding the element, in the page's unit",
    )


class DocumentWord(BaseModel):
    """A single recognised word."""

    content: str = Field(default="", description="Word text")
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Recognition confidence"
    )
    span: TextSpan | None = Field(default=None, description="Span into the extracted text")
    polygon: list[float] = Field(default_factory=list, description="Flattened x,y pairs")


class DocumentLine(BaseModel):
    """A line of text as laid out on the page.

    Lines preserve the line breaks and reading order that the space-joined
    :attr:`PageContent.text` destroys.
    """

    content: str = Field(default="", description="Line text")
    spans: list[TextSpan] = Field(default_factory=list, description="Spans into extracted text")
    polygon: list[float] = Field(default_factory=list, description="Flattened x,y pairs")


class SelectionMark(BaseModel):
    """A checkbox or radio button and whether it is selected."""

    state: str | None = Field(default=None, description="'selected' or 'unselected'")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    spans: list[TextSpan] = Field(default_factory=list)
    polygon: list[float] = Field(default_factory=list)


class TableCell(BaseModel):
    """One cell of a table, positioned in the grid.

    ``row_index``/``column_index`` plus ``row_span``/``column_span`` are what make a table
    reconstructible without re-reading the rendered markdown.
    """

    row_index: int = Field(default=0, ge=0, description="0-indexed row of the cell's origin")
    column_index: int = Field(default=0, ge=0, description="0-indexed column of the cell's origin")
    row_span: int = Field(default=1, ge=1, description="Rows the cell spans")
    column_span: int = Field(default=1, ge=1, description="Columns the cell spans")
    kind: str = Field(
        default="content",
        description="'content', 'columnHeader', 'rowHeader', 'stubHead' or 'description'",
    )
    content: str = Field(default="", description="Cell text")
    elements: list[str] = Field(
        default_factory=list,
        description="References to the elements the cell's content came from",
    )
    spans: list[TextSpan] = Field(default_factory=list)
    bounding_regions: list[BoundingRegion] = Field(default_factory=list)


class ExtractedTable(BaseModel):
    """A table with its cell grid intact."""

    row_count: int = Field(default=0, ge=0, description="Declared number of rows")
    column_count: int = Field(default=0, ge=0, description="Declared number of columns")
    cells: list[TableCell] = Field(default_factory=list)
    caption: str | None = Field(default=None, description="Table caption text")
    footnotes: list[str] = Field(default_factory=list, description="Footnote text")
    spans: list[TextSpan] = Field(default_factory=list)
    bounding_regions: list[BoundingRegion] = Field(default_factory=list)

    @property
    def page_numbers(self) -> list[int]:
        """Pages the table appears on, in order, without duplicates."""
        seen: list[int] = []
        for region in self.bounding_regions:
            if region.page_number not in seen:
                seen.append(region.page_number)
        return seen

    def to_grid(self) -> list[list[str | None]]:
        """Rebuild the table as a ``row_count`` x ``column_count`` grid of cell text.

        Merged cells repeat their content across every position they span. Positions no
        cell covers stay ``None``. Reconstruction relies only on this model — the rendered
        markdown in ``extracted_text`` is not consulted.
        """
        grid: list[list[str | None]] = [
            [None] * self.column_count for _ in range(self.row_count)
        ]
        for cell in self.cells:
            for row in range(cell.row_index, cell.row_index + cell.row_span):
                for col in range(cell.column_index, cell.column_index + cell.column_span):
                    if 0 <= row < self.row_count and 0 <= col < self.column_count:
                        grid[row][col] = cell.content
        return grid


class ExtractedFigure(BaseModel):
    """A figure, chart, or image region."""

    figure_id: str | None = Field(default=None, description="Service-assigned figure id")
    caption: str | None = Field(default=None, description="Figure caption text")
    footnotes: list[str] = Field(default_factory=list)
    elements: list[str] = Field(
        default_factory=list, description="References to elements belonging to the figure"
    )
    spans: list[TextSpan] = Field(default_factory=list)
    bounding_regions: list[BoundingRegion] = Field(default_factory=list)


class ExtractedParagraph(BaseModel):
    """A paragraph and the semantic role the service assigned it."""

    content: str = Field(default="", description="Paragraph text")
    role: str | None = Field(
        default=None,
        description="'title', 'sectionHeading', 'pageHeader', 'pageFooter', 'footnote', ...",
    )
    spans: list[TextSpan] = Field(default_factory=list)
    bounding_regions: list[BoundingRegion] = Field(default_factory=list)


class DocumentSection(BaseModel):
    """A node of the document's section hierarchy."""

    elements: list[str] = Field(
        default_factory=list, description="References to the elements the section contains"
    )
    spans: list[TextSpan] = Field(default_factory=list)


class DocumentStyle(BaseModel):
    """A run of text sharing visual styling."""

    is_handwritten: bool | None = Field(default=None)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    font_style: str | None = Field(default=None)
    font_weight: str | None = Field(default=None)
    color: str | None = Field(default=None)
    background_color: str | None = Field(default=None)
    similar_font_family: str | None = Field(default=None)
    spans: list[TextSpan] = Field(default_factory=list)


class KeyValueElement(BaseModel):
    """One half of a key-value pair."""

    content: str = Field(default="")
    spans: list[TextSpan] = Field(default_factory=list)
    bounding_regions: list[BoundingRegion] = Field(default_factory=list)


class KeyValuePair(BaseModel):
    """A detected form field and its value."""

    key: KeyValueElement = Field(default_factory=KeyValueElement)
    value: KeyValueElement | None = Field(default=None)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class PageContent(BaseModel):
    """Value object representing content extracted from a single page.

    ``text`` is the service's words joined by single spaces and is kept for backward
    compatibility; it loses line breaks and cell boundaries. Prefer ``lines`` when layout
    matters.
    """

    page_number: int = Field(..., ge=1, description="Page number (1-indexed)")
    text: str = Field(default="", description="Extracted text content")
    word_count: int = Field(default=0, ge=0, description="Number of words on the page")

    # Page geometry and structure
    width: float | None = Field(default=None, description="Page width in `unit`")
    height: float | None = Field(default=None, description="Page height in `unit`")
    unit: str | None = Field(default=None, description="Unit of width/height, e.g. 'inch'")
    angle: float | None = Field(default=None, description="Clockwise page skew in degrees")
    spans: list[TextSpan] = Field(default_factory=list)
    lines: list[DocumentLine] = Field(default_factory=list)
    words: list[DocumentWord] = Field(default_factory=list)
    selection_marks: list[SelectionMark] = Field(default_factory=list)


class ExtractionMetadata(BaseModel):
    """Value object for document extraction metadata."""

    page_count: int = Field(default=0, ge=0, description="Total number of pages")
    word_count: int = Field(default=0, ge=0, description="Total word count")
    extraction_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Extraction confidence score"
    )
    extraction_method: str = Field(
        default="azure-document-intelligence",
        description="Method used for extraction",
    )
    api_version: str = Field(default="2024-11-30", description="API version used")

    # What was preserved. A document extracted before structural preservation existed
    # has zero counts and `raw_analysis_stored` false, which is how it is told apart
    # from one where the service genuinely found no structure.
    table_count: int = Field(default=0, ge=0, description="Tables preserved")
    figure_count: int = Field(default=0, ge=0, description="Figures preserved")
    paragraph_count: int = Field(default=0, ge=0, description="Paragraphs preserved")
    raw_analysis_stored: bool = Field(
        default=False,
        description="Whether the verbatim service response was persisted alongside this output",
    )


class MarkdownOutput(BaseModel):
    """
    Value object representing document analysis output.

    This is the primary output stored in the text container.
    """

    file_id: str = Field(..., description="Unique file identifier")
    file_version: int = Field(default=1, ge=1, description="File version number")
    extracted_text: str = Field(default="", description="Full extracted text content")
    pages: list[PageContent] = Field(default_factory=list, description="Per-page content")
    extraction_metadata: ExtractionMetadata = Field(
        default_factory=ExtractionMetadata,
        description="Extraction metadata",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when extraction was performed",
    )

    # Structural elements. Empty means the service reported none — or, for output written
    # before this model existed, that they were discarded; `extraction_metadata` says which.
    tables: list[ExtractedTable] = Field(default_factory=list)
    figures: list[ExtractedFigure] = Field(default_factory=list)
    paragraphs: list[ExtractedParagraph] = Field(default_factory=list)
    sections: list[DocumentSection] = Field(default_factory=list)
    styles: list[DocumentStyle] = Field(default_factory=list)
    key_value_pairs: list[KeyValuePair] = Field(default_factory=list)
    content_format: str | None = Field(
        default=None, description="Format of `extracted_text`, e.g. 'markdown'"
    )
    model_id: str | None = Field(default=None, description="Analysis model, e.g. 'prebuilt-layout'")

    # The verbatim service response, carried for the caller that persists it as a sidecar
    # blob. Excluded from serialisation: text.json holds the typed projection above, and
    # analysis.json holds this. Keeping it here rather than in the port signature means
    # nothing outside infrastructure has to name an Azure SDK type.
    raw_analysis: dict[str, Any] | None = Field(default=None, exclude=True, repr=False)


class DocumentMetadata(BaseModel):
    """Metadata about a document to be processed."""

    file_id: str = Field(..., description="Unique file identifier")
    file_version: int = Field(default=1, ge=1, description="File version number")
    blob_name: str = Field(..., description="Original blob/file name")
    content_type: str = Field(
        default="application/octet-stream",
        description="MIME type of the document",
    )
    size_bytes: int = Field(default=0, ge=0, description="File size in bytes")
    source_container: str = Field(default="raw", description="Source blob container")
    source_path: str = Field(default="", description="Full path in source container")
