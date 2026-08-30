#!/usr/bin/env python3
"""Show what the convert stage keeps from a document, before and after preservation.

Analyses one document with Azure Document Intelligence and prints, side by side, the
extraction output as it was produced before structural preservation and as it is produced
now. The point is to make the difference inspectable on a real document rather than
argued about: the markdown the service returns renders tables as HTML, so the rendered
text cannot stand in for a cell grid.

Usage:
    # Against the bundled sample (a one-page PDF with a merged-header table)
    uv run python scripts/show_extraction_output.py

    # Against your own document
    uv run python scripts/show_extraction_output.py path/to/document.pdf

    # Write the two artefacts the stage would store, for inspection
    uv run python scripts/show_extraction_output.py --dump-to ./extraction-output

Requires DOCUMENT_INTELLIGENCE_ENDPOINT and, unless using managed identity,
DOCUMENT_INTELLIGENCE_API_KEY — the same settings the service reads. One analysis is
billed per run.
"""

import argparse
import asyncio
import json
import mimetypes
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config.settings import get_settings  # noqa: E402
from src.core.entities.document_analysis import MarkdownOutput  # noqa: E402
from src.infrastructure.azure.adapters.document_intelligence_azure import (  # noqa: E402
    AzureDocumentIntelligenceAdapter,
)

# The fields the extractor kept before this change. Everything else it computed was
# discarded on the way out of the adapter.
FIELDS_KEPT_BEFORE = {
    "file_id",
    "file_version",
    "extracted_text",
    "pages",
    "extraction_metadata",
    "created_at",
}
PAGE_FIELDS_KEPT_BEFORE = {"page_number", "text", "word_count"}
METADATA_FIELDS_KEPT_BEFORE = {
    "page_count",
    "word_count",
    "extraction_confidence",
    "extraction_method",
    "api_version",
}


def as_it_was_before(output: MarkdownOutput) -> dict:
    """Reduce a current output to the shape the previous mapper would have produced."""
    before = output.model_dump(mode="json", include=FIELDS_KEPT_BEFORE)
    before["pages"] = [
        {k: v for k, v in page.items() if k in PAGE_FIELDS_KEPT_BEFORE}
        for page in before["pages"]
    ]
    before["extraction_metadata"] = {
        k: v
        for k, v in before["extraction_metadata"].items()
        if k in METADATA_FIELDS_KEPT_BEFORE
    }
    return before


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


async def analyse(content: bytes, content_type: str) -> MarkdownOutput:
    adapter = AzureDocumentIntelligenceAdapter(settings=get_settings().document_intelligence)
    try:
        return await adapter.analyze_document(
            document_content=content,
            content_type=content_type,
            file_id="show-extraction-output",
            file_version=1,
        )
    finally:
        adapter.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "document",
        nargs="?",
        help="Document to analyse. Defaults to the bundled sample PDF.",
    )
    parser.add_argument(
        "--dump-to",
        metavar="DIR",
        help="Write text.json and the raw analysis to DIR for inspection.",
    )
    args = parser.parse_args()

    if args.document:
        path = Path(args.document)
        content = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/pdf"
        source = f"{path} ({len(content):,} bytes, {content_type})"
    else:
        from tests.support.sample_documents import TABLE_ROWS, build_sample_pdf

        content = build_sample_pdf()
        content_type = "application/pdf"
        source = (
            f"generated sample PDF ({len(content):,} bytes) — a heading, a paragraph, and "
            f"this table:\n    " + "\n    ".join(str(row) for row in TABLE_ROWS)
        )

    rule("INPUT")
    print(source)

    output = asyncio.run(analyse(content, content_type))

    rule("WHAT THE SERVICE RETURNED (markdown, first 400 chars)")
    print(output.extracted_text[:400])
    print(
        "\nNote how the table arrives: rendered HTML inside the markdown. Readable, but "
        "not a grid."
    )

    rule("BEFORE — what the extractor used to keep")
    before = as_it_was_before(output)
    print(json.dumps(before, indent=2)[:1200])
    print(
        f"\n  tables: none  figures: none  paragraph roles: none  spans: none\n"
        f"  page fields: {sorted(PAGE_FIELDS_KEPT_BEFORE)}\n"
        f"  serialised size: {len(json.dumps(before)):,} bytes"
    )

    rule("AFTER — what it keeps now")
    after = output.model_dump(mode="json")
    meta = output.extraction_metadata
    print(
        f"  tables: {meta.table_count}  figures: {meta.figure_count}  "
        f"paragraphs: {meta.paragraph_count}  "
        f"roles: {sorted({p.role for p in output.paragraphs if p.role})}\n"
        f"  page fields: width/height/unit/angle, {len(output.pages[0].lines)} lines, "
        f"{len(output.pages[0].words)} words, "
        f"{len(output.pages[0].selection_marks)} selection marks\n"
        f"  serialised size: {len(json.dumps(after)):,} bytes"
    )

    for table in output.tables:
        print(
            f"\n  Table {table.row_count}x{table.column_count} on page(s) "
            f"{table.page_numbers}, caption={table.caption!r}"
        )
        print("  Reconstructed from cells alone (no markdown parsing):")
        for row in table.to_grid():
            print("     ", row)
        merged = [c for c in table.cells if c.row_span > 1 or c.column_span > 1]
        for cell in merged:
            print(
                f"    merged: {cell.content!r} at ({cell.row_index},{cell.column_index}) "
                f"spanning {cell.row_span}x{cell.column_span}, kind={cell.kind}"
            )
        cell = table.cells[0]
        if cell.spans:
            span = cell.spans[0]
            print(
                f"    first cell spans chars {span.offset}..{span.offset + span.length} of "
                f"the markdown → {output.extracted_text[span.offset:span.offset + span.length]!r}"
            )
        if cell.bounding_regions:
            region = cell.bounding_regions[0]
            print(f"    first cell sits on page {region.page_number}, polygon {region.polygon}")

    rule("THE RAW SIDECAR")
    if output.raw_analysis is None:
        print("  none (the fake adapter has no service response to copy)")
    else:
        raw_keys = set(output.raw_analysis)
        modelled = {"apiVersion", "modelId", "content", "contentFormat", "pages",
                    "paragraphs", "tables", "figures", "sections", "styles",
                    "keyValuePairs"}
        print(f"  keys: {sorted(raw_keys)}")
        print(f"  not modelled by text.json, kept only here: {sorted(raw_keys - modelled)}")
        print(f"  serialised size: {len(json.dumps(output.raw_analysis)):,} bytes")

    if args.dump_to:
        out_dir = Path(args.dump_to)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "text.json").write_text(json.dumps(after, indent=2))
        (out_dir / "text.before.json").write_text(json.dumps(before, indent=2))
        if output.raw_analysis is not None:
            (out_dir / "analysis.json").write_text(
                json.dumps(output.raw_analysis, indent=2, default=str)
            )
        rule("WRITTEN")
        for name in sorted(p.name for p in out_dir.iterdir()):
            print(f"  {out_dir / name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
