#!/usr/bin/env python3
"""Run the Docling extraction adapter over a document and show what the stage would store.

This is the fastest way to see the adapter's output on a real document without standing up
the pipeline. It prints the rendered markdown, the canonical block list with the range each
block occupies, and each table's grid — and it checks the output against the same contract
assertions every adapter is held to, so a bad mapping is a failure here rather than a
surprise downstream.

Usage:
    # Against the bundled sample (a one-page PDF with a merged-header table)
    uv run python scripts/extract_with_docling.py

    # Against your own document
    uv run python scripts/extract_with_docling.py path/to/document.pdf

    # Write the artefact the stage would store, for inspection
    uv run python scripts/extract_with_docling.py doc.pdf --dump-to ./docling-output

Requires the optional `docling` extra and its model weights:

    uv sync --extra docling && uv run docling-tools models download

No Azure resources, no credentials, and no per-page billing: the conversion runs in this
process.
"""

import argparse
import asyncio
import json
import mimetypes
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config.settings import get_settings  # noqa: E402
from src.core.entities.document_analysis import MarkdownOutput  # noqa: E402


def load_document(path: Path | None) -> tuple[bytes, str, str]:
    """The bytes to analyse, their content type, and a file id to label them with."""
    if path is None:
        from tests.support.sample_documents import build_sample_pdf

        return build_sample_pdf(), "application/pdf", "sample-document"

    content_type = mimetypes.guess_type(path.name)[0] or "application/pdf"
    return path.read_bytes(), content_type, path.stem


async def extract(content: bytes, content_type: str, file_id: str) -> MarkdownOutput:
    from src.infrastructure.docling.adapter import DoclingExtractionAdapter

    adapter = DoclingExtractionAdapter(settings=get_settings().docling)
    return await adapter.analyze_document(
        document_content=content, content_type=content_type, file_id=file_id
    )


def show(output: MarkdownOutput, elapsed: float) -> None:
    metadata = output.extraction_metadata
    print(f"\n=== {metadata.extraction_method} {metadata.api_version} ===")
    print(
        f"{metadata.page_count} page(s), {metadata.word_count} words, "
        f"{metadata.table_count} table(s), {metadata.figure_count} figure(s) "
        f"in {elapsed:.1f}s"
    )

    print("\n--- extracted text ---")
    print(output.extracted_text)

    print("\n--- blocks, in reading order ---")
    for block in output.blocks:
        page = f"p{block.page_number}" if block.page_number else "p?"
        excerpt = block.text_in(output.extracted_text).replace("\n", " ")[:60]
        print(f"  {page} {block.kind.value:<10} {block.start:>5}..{block.end:<5} {excerpt}")

    for index, table in enumerate(output.tables):
        print(f"\n--- table {index}: {table.row_count}x{table.column_count} ---")
        if table.caption:
            print(f"  caption: {table.caption}")
        print(f"  header rows: {table.header_rows or 'none reported'}")
        for row in table.to_grid():
            print("  | " + " | ".join(cell or "" for cell in row) + " |")
        print(f"  every fragment repeats rows {table.prefix_row_indices or 'none'}")

    # The bar every adapter is held to, run here so this script is a check and not just a
    # printout. A mapping that drops a cell or mislocates a block fails on the spot.
    from tests.support.extractor_contract import assert_satisfies_the_extraction_contract

    assert_satisfies_the_extraction_contract(output)
    print("\nOutput satisfies the canonical extraction contract.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", nargs="?", type=Path, help="Document to analyse")
    parser.add_argument(
        "--dump-to", type=Path, help="Directory to write text.json and analysis.json into"
    )
    args = parser.parse_args()

    if args.document is not None and not args.document.is_file():
        print(f"No such file: {args.document}", file=sys.stderr)
        return 1

    content, content_type, file_id = load_document(args.document)
    started = time.time()
    output = asyncio.run(extract(content, content_type, file_id))
    show(output, time.time() - started)

    if args.dump_to:
        args.dump_to.mkdir(parents=True, exist_ok=True)
        # The same two artefacts the stage writes: the typed projection, and the verbatim
        # DoclingDocument that `analysis_format` identifies.
        (args.dump_to / "text.json").write_text(output.model_dump_json(indent=2))
        (args.dump_to / "analysis.json").write_text(
            json.dumps(output.raw_analysis, indent=2, default=str)
        )
        print(f"\nWrote text.json and analysis.json to {args.dump_to}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
