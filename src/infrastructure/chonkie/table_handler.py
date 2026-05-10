"""HTML table extraction and handling for structure-aware chunking."""

import re
from dataclasses import dataclass, field


@dataclass
class TableBlock:
    """Represents an extracted HTML table block."""

    table_id: str
    html: str
    start_index: int
    end_index: int
    placeholder: str


def _find_outermost_tables(text: str) -> list[tuple[int, int]]:
    """Find outermost <table>...</table> spans, handling nesting.

    For nested tables, we only capture the outermost boundary.

    Returns list of (start, end) tuples.
    """
    spans: list[tuple[int, int]] = []
    depth = 0
    start = -1

    open_tag = re.compile(r"<table[\s>]", re.IGNORECASE)
    close_tag = re.compile(r"</table\s*>", re.IGNORECASE)

    i = 0
    while i < len(text):
        open_match = open_tag.search(text, i)
        close_match = close_tag.search(text, i)

        if open_match is None and close_match is None:
            break

        # Determine which comes first
        open_pos = open_match.start() if open_match else len(text)
        close_pos = close_match.start() if close_match else len(text)

        if open_pos <= close_pos:
            if depth == 0:
                start = open_pos
            depth += 1
            i = open_pos + 1
        else:
            depth -= 1
            if depth == 0 and start >= 0:
                end = close_match.end()  # type: ignore[union-attr]
                spans.append((start, end))
                start = -1
            if depth < 0:
                depth = 0
            i = close_pos + 1

    return spans


def extract_tables(text: str) -> tuple[str, list[TableBlock]]:
    """Extract HTML table blocks from text, replacing them with placeholders.

    Args:
        text: Markdown text potentially containing HTML <table> blocks.

    Returns:
        Tuple of (modified text with placeholders, list of extracted TableBlock objects).
        Tables are extracted in order of appearance.
    """
    spans = _find_outermost_tables(text)
    if not spans:
        return text, []

    tables: list[TableBlock] = []
    # Process in reverse order to preserve indices when replacing
    modified = text
    for idx, (start, end) in enumerate(reversed(spans)):
        table_index = len(spans) - 1 - idx
        table_id = f"table_{table_index}"
        placeholder = f"<!-- TABLE_PLACEHOLDER_{table_index} -->"
        html = text[start:end]

        tables.insert(
            0,
            TableBlock(
                table_id=table_id,
                html=html,
                start_index=start,
                end_index=end,
                placeholder=placeholder,
            ),
        )
        modified = modified[:start] + placeholder + modified[end:]

    return modified, tables


def get_placeholder_pattern() -> re.Pattern[str]:
    """Get compiled regex for matching table placeholders."""
    return re.compile(r"<!-- TABLE_PLACEHOLDER_(\d+) -->")
