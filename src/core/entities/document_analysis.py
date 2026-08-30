"""The canonical extraction model: what the `convert` stage emits, whoever produced it.

These value objects describe a document's structure — an ordered block list, tables with
their cell grid, figures, paragraphs, sections, styles, key-value pairs, and per-page
lines, words and selection marks — in terms that name no extraction service. Azure
Document Intelligence is the only adapter today; the model is designed so that adding
another one is an adapter and not a change to any consumer.

Four properties are deliberate and load-bearing:

- **Every block resolves against the text.** A :class:`ContentBlock` carries ``(start,
  end)`` into :attr:`MarkdownOutput.extracted_text`, and the *adapter* guarantees that,
  whether its provider reports offsets (Document Intelligence does) or the adapter
  produced them while rendering the text itself (a Docling adapter would). No consumer
  needs to know which happened.
- **The adapter renders; the consumer never parses.** A table carries ``rendered`` — its
  text exactly as it appears in ``extracted_text`` — plus ``render_prefix``, ``rows`` and
  ``render_suffix``, so a consumer emitting *part* of a table composes strings instead of
  pattern-matching HTML or pipe syntax. See :class:`ExtractedTable` for the composition
  rule and the exactness guarantee that backs it.
- **Provider vocabulary is normalised, geometry is not.** Cell roles become
  :class:`CellRole`; a :class:`BoundingBox` records its ``unit`` and ``origin`` rather
  than being converted, because a converted number carries a conversion no consumer can
  see. Provider element references are preserved verbatim and interpreted by nobody.
- **The model is additive.** ``extracted_text``, ``pages[].text``, ``pages[].word_count``
  and the original ``ExtractionMetadata`` fields keep their meaning, so a ``text.json``
  written before this model existed still deserialises — with an empty ``blocks``, which
  consumers must read as "structure unavailable" rather than "document without
  structure".
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


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


class BlockKind(StrEnum):
    """What a block of the document is, in terms no extraction service owns."""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    FIGURE = "figure"
    CAPTION = "caption"
    LIST_ITEM = "list_item"
    OTHER = "other"


class CellRole(StrEnum):
    """What a table cell is, canonically.

    Document Intelligence spells these as a ``kind`` string
    (``columnHeader``/``rowHeader``/``stubHead``); Docling as three booleans
    (``column_header``/``row_header``/``row_section``). Both map onto this.
    """

    CONTENT = "content"
    COLUMN_HEADER = "column_header"
    ROW_HEADER = "row_header"
    SECTION_ROW = "section_row"
    STUB_HEAD = "stub_head"


# Provider spellings that mean the same thing as a canonical role. `description` has no
# canonical twin — Document Intelligence uses it for explanatory cells that are not
# headers — so it lands on `content`; the provider's own spelling stays recoverable from
# the raw analysis sidecar.
_CELL_ROLE_ALIASES: dict[str, CellRole] = {
    "content": CellRole.CONTENT,
    "columnheader": CellRole.COLUMN_HEADER,
    "column_header": CellRole.COLUMN_HEADER,
    "rowheader": CellRole.ROW_HEADER,
    "row_header": CellRole.ROW_HEADER,
    "rowsection": CellRole.SECTION_ROW,
    "row_section": CellRole.SECTION_ROW,
    "section_row": CellRole.SECTION_ROW,
    "stubhead": CellRole.STUB_HEAD,
    "stub_head": CellRole.STUB_HEAD,
    "description": CellRole.CONTENT,
}

HEADER_CELL_ROLES: frozenset[CellRole] = frozenset(
    {CellRole.COLUMN_HEADER, CellRole.ROW_HEADER, CellRole.STUB_HEAD}
)
"""The roles that make a row part of a table's header.

``SECTION_ROW`` is deliberately absent: a section row groups body rows, it does not label
the columns, and repeating it above an arbitrary fragment would assert a grouping the
document does not show.
"""


def cell_role_from(value: object) -> CellRole:
    """Map a provider's spelling of a cell role onto the canonical one.

    Anything unrecognised becomes :attr:`CellRole.CONTENT`: a role we cannot name is a
    cell whose contribution to the header is unknown, and guessing it into the header
    would repeat a data row above every fragment of the table.
    """
    if isinstance(value, CellRole):
        return value
    if value is None:
        return CellRole.CONTENT
    return _CELL_ROLE_ALIASES.get(str(value).strip().lower(), CellRole.CONTENT)


class CoordinateUnit(StrEnum):
    """The unit a bounding box's coordinates are in."""

    INCH = "inch"
    POINT = "point"
    PIXEL = "pixel"


class CoordinateOrigin(StrEnum):
    """Which corner of the page a bounding box's coordinates are measured from."""

    TOP_LEFT = "top_left"
    BOTTOM_LEFT = "bottom_left"


class BoundingBox(BaseModel):
    """Where something sits on a page, with the units it is measured in.

    Document Intelligence reports inches from a top-left origin; Docling reports points
    and can use either origin. Neither is converted on the way in: ``unit`` and ``origin``
    are recorded so that a consumer comparing geometry across documents can check them,
    rather than silently comparing incompatible numbers.
    """

    page_number: int = Field(..., ge=1, description="1-indexed page the box is on")
    left: float = Field(..., description="Smallest x coordinate, in `unit`")
    top: float = Field(..., description="Smallest y coordinate from `origin`, in `unit`")
    right: float = Field(..., description="Largest x coordinate, in `unit`")
    bottom: float = Field(..., description="Largest y coordinate from `origin`, in `unit`")
    unit: CoordinateUnit = Field(..., description="Unit the coordinates are in")
    origin: CoordinateOrigin = Field(..., description="Corner the coordinates start from")
    polygon: list[float] = Field(
        default_factory=list,
        description="The provider's own flattened x,y pairs, kept when it supplies them",
    )


class ContentBlock(BaseModel):
    """One element of the document, in reading order, located in the extracted text.

    ``start`` and ``end`` index into :attr:`MarkdownOutput.extracted_text` and yield this
    block's text. That invariant is the adapter's responsibility — see the port docstring
    — and holds regardless of how the provider reports position.

    Blocks do not overlap and do not nest: a block that a table or figure encloses (a
    cell's paragraph, a caption) is reachable through that table or figure rather than
    appearing twice in the list.
    """

    kind: BlockKind = Field(default=BlockKind.PARAGRAPH, description="What this block is")
    start: int = Field(default=0, ge=0, description="Start index into the extracted text")
    end: int = Field(default=0, ge=0, description="End index (exclusive) into the extracted text")
    page_number: int | None = Field(
        default=None, ge=1, description="Page the block starts on, when the provider says"
    )
    bounding_box: BoundingBox | None = Field(
        default=None, description="Where the block sits on the page, when known"
    )
    role: str | None = Field(
        default=None,
        description="The provider's own role for the block, preserved beside the canonical kind",
    )
    table_index: int | None = Field(
        default=None,
        description="For a table block, its index in `MarkdownOutput.tables`",
    )
    elements: list[str] = Field(
        default_factory=list,
        description="The provider's references to related elements, opaque and uninterpreted",
    )

    @property
    def length(self) -> int:
        """Characters the block occupies in the extracted text."""
        return self.end - self.start

    def text_in(self, extracted_text: str) -> str:
        """The block's text, resolved against the text it was located in."""
        return extracted_text[self.start : self.end]


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
    role: CellRole = Field(
        default=CellRole.CONTENT,
        description="What the cell is, canonically, rather than in the provider's spelling",
    )
    content: str = Field(default="", description="Cell text")
    elements: list[str] = Field(
        default_factory=list,
        description="References to the elements the cell's content came from",
    )
    spans: list[TextSpan] = Field(default_factory=list)
    bounding_regions: list[BoundingRegion] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _accept_provider_kind(cls, data: Any) -> Any:
        """Read the pre-canonical ``kind`` when no ``role`` is given.

        A ``text.json`` written before this model — and a caller still passing
        ``kind="columnHeader"`` — must keep working, so the old spelling is mapped rather
        than rejected. An explicit ``role`` always wins.
        """
        if isinstance(data, dict) and "role" not in data and "kind" in data:
            data = {**data, "role": cell_role_from(data["kind"])}
            data.pop("kind", None)
        return data

    @property
    def kind(self) -> str:
        """Deprecated alias for :attr:`role`. Reports the canonical spelling, not the
        provider's — read ``role`` instead."""
        return self.role.value

    @property
    def is_header(self) -> bool:
        """Whether this cell makes its rows part of the table's header."""
        return self.role in HEADER_CELL_ROLES


class TableRow(BaseModel):
    """One rendered body row of a table.

    A row exists so that a consumer can emit *some* of a table without knowing how the
    extractor renders one. ``rendered`` is that row's text exactly as it appears inside
    :attr:`ExtractedTable.rendered`; the composition rule that turns rows back into a
    valid table lives on :class:`ExtractedTable`.
    """

    row_index: int = Field(
        default=0,
        ge=0,
        description="The row's index in the table's grid, shared with the rows the prefix carries",
    )
    rendered: str = Field(default="", description="The row's text as the extractor rendered it")
    source_range: tuple[int, int] | None = Field(
        default=None,
        description=(
            "Where the row's rendering sits in the extracted text, when that range is "
            "contiguous; None rather than an approximation when it is not"
        ),
    )
    continues_from_row: int | None = Field(
        default=None,
        description=(
            "The earlier row a vertically merged cell ties this one to, making the two "
            "inseparable; None when the row stands alone"
        ),
    )


class ExtractedTable(BaseModel):
    """A table with its cell grid intact and its rendering partitioned for reuse.

    **Fragment composition.** A consumer that needs some rows of a table composes
    ``render_prefix`` + those rows' ``rendered`` in document order + ``render_suffix``,
    and does nothing else — :meth:`fragment` is that concatenation. The result is a valid
    table in whatever form the extractor produced, because ``render_prefix`` is *exactly*
    the part of ``rendered`` preceding the first body row — whatever that form requires
    there, including a Markdown pipe table's header and delimiter lines — and
    ``render_suffix`` is exactly the part following the last.

    **The exactness rule.** The fragment composed from *every* body row equals
    ``rendered`` byte for byte. The adapter guarantees it by partitioning a string it
    already has rather than reassembling one from cell spans, which cover cell content
    only and exclude the markup around it.

    ``prefix_row_indices`` names the rows ``render_prefix`` carries — the rows every
    fragment therefore repeats. It is not the same set as ``header_rows``, which is
    semantic: a header row the prefix does not carry stays an ordinary body row in
    document order.
    """

    row_count: int = Field(default=0, ge=0, description="Declared number of rows")
    column_count: int = Field(default=0, ge=0, description="Declared number of columns")
    cells: list[TableCell] = Field(default_factory=list)
    caption: str | None = Field(default=None, description="Table caption text")
    footnotes: list[str] = Field(default_factory=list, description="Footnote text")
    spans: list[TextSpan] = Field(default_factory=list)
    bounding_regions: list[BoundingRegion] = Field(default_factory=list)

    header_rows: list[int] = Field(
        default_factory=list,
        description=(
            "Row indices forming the table's header, derived from cell roles rather than "
            "assumed to be the leading rows"
        ),
    )
    rendered: str = Field(
        default="",
        description="The table's text exactly as it appears in the extracted text",
    )
    render_prefix: str = Field(
        default="",
        description="Exactly the part of `rendered` preceding the first body row",
    )
    prefix_row_indices: list[int] = Field(
        default_factory=list,
        description="The rows `render_prefix` carries, and that every fragment repeats",
    )
    render_suffix: str = Field(
        default="",
        description="Exactly the part of `rendered` following the last body row",
    )
    rows: list[TableRow] = Field(
        default_factory=list,
        description="The body rows — the remainder of `rendered` — in document order",
    )

    def fragment(self, rows: list[TableRow] | None = None) -> str:
        """Render a selection of body rows as a table in the extractor's own form.

        With no argument this returns every body row, which is ``rendered`` byte for byte
        for a contiguously rendered table — the exactness rule. Rows are emitted in the
        order given, so a caller preserving document order passes a slice of
        :attr:`rows`.
        """
        selected = self.rows if rows is None else rows
        return self.render_prefix + "".join(row.rendered for row in selected) + self.render_suffix

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

    # The canonical block list: the document's elements in reading order, each located in
    # `extracted_text`. Empty means structure is *unavailable* — output written before the
    # block list existed — not a document that has none.
    blocks: list[ContentBlock] = Field(default_factory=list)

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
