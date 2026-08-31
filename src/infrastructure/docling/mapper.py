"""Turning a `DoclingDocument` into the canonical extraction model.

Docling hands back a document tree, not a string. The Azure adapter receives markdown with
the service's own offsets into it; this one has neither, so it **renders the markdown
itself and records each element's range as it writes** — the second half of the offset
invariant the port states, and the reason this module produces the text rather than
calling `DoclingDocument.export_to_markdown()` and searching it afterwards. Searching a
rendering for the text that produced it is guesswork the moment a phrase repeats.

Two consequences worth stating, because both look like omissions:

- The markdown here is *this adapter's* markdown, not byte-identical to Docling's own
  export. It is the same content in the same order; where they differ, this one is the
  authority, because it is the string the offsets are into.
- `spans`, `styles` and `key_value_pairs` are left empty. Docling reports no character
  spans into any markdown, no visual styling, and no form fields through this pipeline;
  synthesising them would mean inventing offsets into a string Docling never saw. The
  canonical model reads an empty list as "the engine reported none", which is true.
"""

import logging
from datetime import datetime

from docling_core.types.doc.document import (
    CodeItem,
    DocItem,
    DoclingDocument,
    FormulaItem,
    ListItem,
    PictureItem,
    SectionHeaderItem,
    TableItem,
    TextItem,
    TitleItem,
)
from docling_core.types.doc.labels import DocItemLabel

from src.core.entities.document_analysis import (
    BlockKind,
    BoundingBox,
    BoundingRegion,
    ContentBlock,
    CoordinateOrigin,
    CoordinateUnit,
    DocumentLine,
    ExtractedFigure,
    ExtractedParagraph,
    ExtractedTable,
    ExtractionMetadata,
    MarkdownOutput,
    PageContent,
    TableCell,
    TextSpan,
    cell_role_from,
)
from src.infrastructure.extraction.tables import (
    header_rows_from_cells,
    partition_pipe_table,
    row_continuations_from_cells,
)

logger = logging.getLogger(__name__)

EXTRACTION_METHOD = "docling"
ANALYSIS_FORMAT = "docling-document"

# What separates two rendered elements, and therefore what every offset in this module is
# arithmetic over. A blank line, because that is what makes consecutive markdown elements
# distinct rather than one reflowed paragraph.
_BLOCK_SEPARATOR = "\n\n"

# Docling's labels mapped onto the canonical kinds, explicitly rather than by name
# coincidence. The two vocabularies are close enough that a lookup by string would mostly
# work and would be wrong in exactly the interesting places — `caption` and `footnote` both
# read as prose, `document_index` is a table of contents and not a table.
_BLOCK_KINDS: dict[DocItemLabel, BlockKind] = {
    DocItemLabel.TITLE: BlockKind.HEADING,
    DocItemLabel.SECTION_HEADER: BlockKind.HEADING,
    DocItemLabel.TABLE: BlockKind.TABLE,
    DocItemLabel.PICTURE: BlockKind.FIGURE,
    DocItemLabel.CHART: BlockKind.FIGURE,
    DocItemLabel.CAPTION: BlockKind.CAPTION,
    DocItemLabel.LIST_ITEM: BlockKind.LIST_ITEM,
    DocItemLabel.TEXT: BlockKind.PARAGRAPH,
    DocItemLabel.PARAGRAPH: BlockKind.PARAGRAPH,
    DocItemLabel.FOOTNOTE: BlockKind.PARAGRAPH,
    DocItemLabel.PAGE_HEADER: BlockKind.PARAGRAPH,
    DocItemLabel.PAGE_FOOTER: BlockKind.PARAGRAPH,
    DocItemLabel.REFERENCE: BlockKind.PARAGRAPH,
    DocItemLabel.CODE: BlockKind.OTHER,
    DocItemLabel.FORMULA: BlockKind.OTHER,
    DocItemLabel.DOCUMENT_INDEX: BlockKind.OTHER,
}

# Labels whose text is prose a reader would call a paragraph. Everything else — a table,
# a picture, a code block — is reachable through its own structural list, so listing it as
# a paragraph too would say the document contains it twice.
_PARAGRAPH_LABELS = frozenset(
    {
        DocItemLabel.TITLE,
        DocItemLabel.SECTION_HEADER,
        DocItemLabel.TEXT,
        DocItemLabel.PARAGRAPH,
        DocItemLabel.LIST_ITEM,
        DocItemLabel.CAPTION,
        DocItemLabel.FOOTNOTE,
        DocItemLabel.PAGE_HEADER,
        DocItemLabel.PAGE_FOOTER,
        DocItemLabel.REFERENCE,
    }
)

# Docling reports PDF geometry in typographic points. It is not read off the document —
# the page size carries no unit — so it is stated here rather than guessed per document,
# and recorded on every box so nothing compares it against the Azure adapter's inches.
_DOCLING_UNIT = CoordinateUnit.POINT

_ORIGINS: dict[str, CoordinateOrigin] = {
    "TOPLEFT": CoordinateOrigin.TOP_LEFT,
    "BOTTOMLEFT": CoordinateOrigin.BOTTOM_LEFT,
}


class _Rendered:
    """One element, its markdown, and where that markdown landed in the document."""

    __slots__ = ("item", "text", "start", "end")

    def __init__(self, item: DocItem, text: str, start: int) -> None:
        self.item = item
        self.text = text
        self.start = start
        self.end = start + len(text)


def map_document(
    document: DoclingDocument,
    file_id: str,
    file_version: int = 1,
    api_version: str = "",
    confidence: float = 0.0,
) -> MarkdownOutput:
    """Project a `DoclingDocument` onto `MarkdownOutput`, rendering the text as we go."""
    rendered = _render(document)
    extracted_text = _BLOCK_SEPARATOR.join(part.text for part in rendered)

    tables: list[ExtractedTable] = []
    figures: list[ExtractedFigure] = []
    paragraphs: list[ExtractedParagraph] = []
    blocks: list[ContentBlock] = []

    for part in rendered:
        label = part.item.label
        block = ContentBlock(
            kind=_BLOCK_KINDS.get(label, BlockKind.OTHER),
            start=part.start,
            end=part.end,
            page_number=_page_of(part.item),
            bounding_box=_bounding_box(part.item),
            # The narrowing to a canonical kind is lossy; Docling's own label rides along,
            # so a consumer that cares about `page_footer` can still see it.
            role=str(label.value if hasattr(label, "value") else label),
        )

        if isinstance(part.item, TableItem):
            block.table_index = len(tables)
            tables.append(_map_table(part, document))
        elif isinstance(part.item, PictureItem):
            figures.append(_map_figure(part, document))
        elif label in _PARAGRAPH_LABELS and isinstance(part.item, TextItem):
            paragraphs.append(
                ExtractedParagraph(
                    content=part.item.text or "",
                    role=block.role,
                    spans=[TextSpan(offset=part.start, length=part.end - part.start)],
                    bounding_regions=_regions(part.item),
                )
            )

        blocks.append(block)

    pages = _map_pages(document, rendered, extracted_text)

    return MarkdownOutput(
        file_id=file_id,
        file_version=file_version,
        extracted_text=extracted_text,
        pages=pages,
        extraction_metadata=ExtractionMetadata(
            page_count=len(pages),
            word_count=len(extracted_text.split()),
            extraction_confidence=round(max(0.0, min(1.0, confidence)), 4),
            extraction_method=EXTRACTION_METHOD,
            api_version=api_version,
            analysis_format=ANALYSIS_FORMAT,
            table_count=len(tables),
            figure_count=len(figures),
            paragraph_count=len(paragraphs),
            # Flipped by whoever actually writes the sidecar; the adapter only supplies it.
            raw_analysis_stored=False,
        ),
        created_at=datetime.utcnow(),
        blocks=blocks,
        tables=tables,
        figures=figures,
        paragraphs=paragraphs,
        content_format="markdown",
        model_id="docling-layout",
        raw_analysis=document.export_to_dict(),
    )


def _render(document: DoclingDocument) -> list[_Rendered]:
    """Render every item in reading order, recording the range each one occupies.

    `iterate_items` walks the body in document order and does not descend into pictures,
    and a table's cells are not items — so no element here encloses another, and the
    disjointness the canonical model requires holds by construction rather than by a
    later sweep.
    """
    parts: list[_Rendered] = []
    offset = 0

    for item, _level in document.iterate_items():
        if not isinstance(item, DocItem):
            continue
        text = _render_item(item, document)
        if not text:
            continue
        parts.append(_Rendered(item, text, offset))
        offset += len(text) + len(_BLOCK_SEPARATOR)

    return parts


def _render_item(item: DocItem, document: DoclingDocument) -> str:
    """The markdown for one item, or "" for one that renders to nothing.

    An item that renders empty is dropped rather than emitted as a zero-length block: a
    block covering no characters resolves against any text at all and so asserts nothing.
    """
    if isinstance(item, TableItem):
        # Docling's own table renderer, so the pipe table is the one its users expect —
        # and, being a string this module then partitions rather than reassembles, the
        # exactness rule holds by construction.
        #
        # Called *without* the document deliberately, though that overload is deprecated:
        # the document-aware one prepends the caption, and a table block whose rendering
        # opened with a line of prose would not be a table under any fragment. The caption
        # is an item of its own and is rendered where it sits, immediately before this.
        return item.export_to_markdown().strip()
    if isinstance(item, PictureItem):
        return "<!-- image -->"
    if isinstance(item, TitleItem):
        return f"# {item.text}".strip()
    if isinstance(item, SectionHeaderItem):
        # Docling levels start at 1; the title already took `#`, so a level-1 header is `##`.
        return f"{'#' * min(6, (item.level or 1) + 1)} {item.text}".strip()
    if isinstance(item, ListItem):
        marker = item.marker if item.enumerated and item.marker else "-"
        return f"{marker} {item.text}".strip()
    if isinstance(item, CodeItem):
        return f"```\n{item.text}\n```"
    if isinstance(item, FormulaItem):
        return f"$${item.text}$$" if item.text else ""
    if isinstance(item, TextItem):
        return (item.text or "").strip()
    return ""


def _map_table(part: _Rendered, document: DoclingDocument) -> ExtractedTable:
    """Map one table: the cell grid, plus the rendering partitioned for reuse.

    Docling spells a cell's role as three booleans where Document Intelligence spells it as
    a string; both land on `CellRole` here, and `header_rows` is derived from those cells
    rather than assumed to be the leading row.
    """
    table: TableItem = part.item  # type: ignore[assignment]
    data = table.data
    cells = [
        TableCell(
            row_index=cell.start_row_offset_idx,
            column_index=cell.start_col_offset_idx,
            row_span=max(1, cell.end_row_offset_idx - cell.start_row_offset_idx),
            column_span=max(1, cell.end_col_offset_idx - cell.start_col_offset_idx),
            role=cell_role_from(_cell_role(cell)),
            content=cell.text or "",
            bounding_regions=(
                [BoundingRegion(page_number=_page_of(table) or 1, polygon=_polygon(cell.bbox))]
                if cell.bbox is not None
                else []
            ),
        )
        for cell in (data.table_cells if data else [])
    ]

    header_rows = header_rows_from_cells(cells)
    partition = partition_pipe_table(
        rendered=part.text,
        header_rows=header_rows,
        continuations=row_continuations_from_cells(cells),
        source_offset=part.start,
    )

    return ExtractedTable(
        row_count=data.num_rows if data else 0,
        column_count=data.num_cols if data else 0,
        cells=cells,
        caption=_caption(table, document),
        footnotes=[],
        spans=[TextSpan(offset=part.start, length=part.end - part.start)],
        bounding_regions=_regions(table),
        header_rows=header_rows,
        rendered=part.text,
        render_prefix=partition.prefix,
        prefix_row_indices=partition.prefix_row_indices,
        render_suffix=partition.suffix,
        rows=partition.rows,
    )


def _cell_role(cell) -> str:
    """Docling's three booleans, read in the order that resolves their overlaps.

    A cell can be both a column header and a row header — the corner of a cross-tabulation
    — and that is exactly what `stub_head` names, so it is checked first.
    """
    if cell.column_header and cell.row_header:
        return "stub_head"
    if cell.column_header:
        return "column_header"
    if cell.row_header:
        return "row_header"
    if cell.row_section:
        return "row_section"
    return "content"


def _map_figure(part: _Rendered, document: DoclingDocument) -> ExtractedFigure:
    """Map one picture."""
    picture: PictureItem = part.item  # type: ignore[assignment]
    return ExtractedFigure(
        figure_id=picture.self_ref,
        caption=_caption(picture, document),
        footnotes=[],
        elements=[],
        spans=[TextSpan(offset=part.start, length=part.end - part.start)],
        bounding_regions=_regions(picture),
    )


def _map_pages(
    document: DoclingDocument, rendered: list[_Rendered], extracted_text: str
) -> list[PageContent]:
    """Per-page content, built from the blocks that start on each page.

    An element straddling a page break counts as belonging to the page it starts on, which
    is the same rule `ContentBlock.page_number` uses. Pages Docling declares but attributes
    no item to still appear, with empty text — a blank page is a fact about the document.
    """
    by_page: dict[int, list[_Rendered]] = {}
    for part in rendered:
        page = _page_of(part.item)
        if page is not None:
            by_page.setdefault(page, []).append(part)

    page_numbers = sorted(set(document.pages) | set(by_page))
    pages: list[PageContent] = []
    for number in page_numbers:
        parts = by_page.get(number, [])
        text = _BLOCK_SEPARATOR.join(part.text for part in parts)
        size = getattr(document.pages.get(number), "size", None)
        pages.append(
            PageContent(
                page_number=number,
                text=text,
                word_count=len(text.split()),
                width=getattr(size, "width", None),
                height=getattr(size, "height", None),
                unit=_DOCLING_UNIT.value,
                spans=[
                    TextSpan(offset=part.start, length=part.end - part.start) for part in parts
                ],
                lines=[
                    line
                    for part in parts
                    for line in _lines_of(part, extracted_text)
                ],
            )
        )
    return pages


def _lines_of(part: _Rendered, extracted_text: str) -> list[DocumentLine]:
    """Split one rendered element into lines that resolve against the document text."""
    lines: list[DocumentLine] = []
    offset = part.start
    for raw in part.text.split("\n"):
        if raw.strip():
            lines.append(
                DocumentLine(
                    content=raw,
                    spans=[TextSpan(offset=offset, length=len(raw))],
                )
            )
        offset += len(raw) + 1
    return lines


def _page_of(item: DocItem) -> int | None:
    """The page an item starts on, when Docling reports provenance for it."""
    prov = getattr(item, "prov", None) or []
    return prov[0].page_no if prov else None


def _regions(item: DocItem) -> list[BoundingRegion]:
    """Every page the item touches, with the polygon Docling reported there."""
    return [
        BoundingRegion(page_number=p.page_no, polygon=_polygon(p.bbox))
        for p in (getattr(item, "prov", None) or [])
    ]


def _bounding_box(item: DocItem) -> BoundingBox | None:
    """The item's box on the page it starts on, in Docling's own unit and origin.

    Nothing is converted. Docling's origin for a PDF is bottom-left where Document
    Intelligence's is top-left, and a converted number would carry a conversion no consumer
    could see — so the origin is recorded and the comparison is the consumer's to make.
    `top` and `bottom` still mean smallest and largest coordinate *from that origin*, which
    is why they are ordered here rather than copied across.
    """
    prov = getattr(item, "prov", None) or []
    if not prov:
        return None
    box = prov[0].bbox
    origin = _ORIGINS.get(str(getattr(box.coord_origin, "value", box.coord_origin)).upper())
    if origin is None:
        logger.warning("Unknown Docling coordinate origin %r; box dropped", box.coord_origin)
        return None
    return BoundingBox(
        page_number=prov[0].page_no,
        left=min(box.l, box.r),
        top=min(box.t, box.b),
        right=max(box.l, box.r),
        bottom=max(box.t, box.b),
        unit=_DOCLING_UNIT,
        origin=origin,
        polygon=_polygon(box),
    )


def _polygon(box) -> list[float]:
    """A Docling rectangle as the flattened x,y pairs the canonical model carries."""
    if box is None:
        return []
    return [box.l, box.t, box.r, box.t, box.r, box.b, box.l, box.b]


def _caption(item, document: DoclingDocument) -> str | None:
    """The item's caption text, when it has one.

    The caption is *also* rendered as a block of its own, where the document puts it. That
    is not duplication of the kind the block list forbids: the block says where the caption
    sits in the text, and this says which table it belongs to, and neither answers the
    other's question.
    """
    return item.caption_text(document) or None
