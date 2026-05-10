"""Metadata helpers for structure-aware chunking: section path, page tracking, and token counting."""

import bisect
import re

import tiktoken

# Regex to match markdown headings (# through ######)
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)$", re.MULTILINE)

# Regex to match Document Intelligence page number comments
_PAGE_NUMBER_PATTERN = re.compile(r'<!--\s*PageNumber="([^"]+)"\s*-->')
# Regex to match Document Intelligence page break comments
_PAGE_BREAK_PATTERN = re.compile(r"<!--\s*PageBreak\s*-->")

# Default tiktoken encoding for OpenAI models
_DEFAULT_ENCODING = "cl100k_base"

# Module-level cache for tiktoken encodings to avoid repeated lookups
_encoding_cache: dict[str, tiktoken.Encoding] = {}


def _normalize_page_label(raw_value: str) -> str | None:
    """Normalize a raw page label from a PageNumber marker."""
    normalized = re.sub(r"^[\-\s]+|[\-\s]+$", "", raw_value.strip())
    return normalized or None


def count_tokens(text: str, encoding_name: str = _DEFAULT_ENCODING) -> int:
    """Count tokens in text using tiktoken.

    Args:
        text: Text to count tokens for.
        encoding_name: Tiktoken encoding name (default: cl100k_base for GPT-4).

    Returns:
        Number of tokens.
    """
    if encoding_name not in _encoding_cache:
        _encoding_cache[encoding_name] = tiktoken.get_encoding(encoding_name)
    return len(_encoding_cache[encoding_name].encode(text))


class HeadingTracker:
    """Track markdown heading hierarchy to build section paths.

    Parses headings from markdown text and maintains a hierarchy stack
    so that given any character offset, we can determine the current
    section path (list of heading texts from root to current level).
    """

    def __init__(self, text: str) -> None:
        """Parse all headings from the text and store them with positions.

        Args:
            text: Full markdown text to parse headings from.
        """
        self._headings: list[tuple[int, int, str]] = []  # (position, level, text)

        for match in _HEADING_PATTERN.finditer(text):
            level = len(match.group(1))
            heading_text = match.group(2).strip()
            position = match.start()
            self._headings.append((position, level, heading_text))

    def section_path_at(self, char_offset: int) -> list[str]:
        """Get the section path (heading hierarchy) at a given character offset.

        Args:
            char_offset: Character offset in the original text.

        Returns:
            List of heading texts from outermost to innermost, e.g.
            ["Introduction", "Background", "Related Work"].
        """
        # Collect all headings that appear before this offset
        relevant = [h for h in self._headings if h[0] <= char_offset]
        if not relevant:
            return []

        # Build the hierarchy: for each heading, pop all headings at same or deeper level
        stack: list[tuple[int, str]] = []  # (level, text)
        for _, level, text in relevant:
            # Remove all headings at same or deeper level
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, text))

        return [text for _, text in stack]

    @property
    def headings(self) -> list[tuple[int, int, str]]:
        """Get all parsed headings as (position, level, text) tuples."""
        return list(self._headings)


class PageTracker:
    """Track page boundaries from Document Intelligence markdown comments.

    Uses ``<!-- PageBreak -->`` markers to infer physical page order and
    ``<!-- PageNumber="..." -->`` markers to resolve optional printed labels.
    """

    def __init__(self, text: str) -> None:
        """Parse all page markers from the text.

        Args:
            text: Full markdown text to parse page markers from.
        """
        self._page_break_positions: list[int] = []
        self._label_positions: list[int] = []
        self._labels: list[str] = []

        for match in _PAGE_BREAK_PATTERN.finditer(text):
            self._page_break_positions.append(match.start())

        for match in _PAGE_NUMBER_PATTERN.finditer(text):
            page_label = _normalize_page_label(match.group(1))
            if page_label is None:
                continue
            self._label_positions.append(match.start())
            self._labels.append(page_label)

    def page_at(self, char_offset: int) -> int | None:
        """Get the physical page number at a given character offset.

        Physical pages are inferred from page breaks:
        - page 1 starts at the beginning of the document
        - each ``<!-- PageBreak -->`` advances to the next page

        Args:
            char_offset: Character offset in the original text.

        Returns:
            1-based physical page number, or None if no page structure exists.
        """
        has_page_structure = bool(self._page_break_positions or self._label_positions)
        if not has_page_structure:
            return None
        return bisect.bisect_right(self._page_break_positions, char_offset) + 1

    def page_label_at(self, char_offset: int) -> str | None:
        """Get the printed page label at a given character offset.

        Returns the latest valid label marker in the current physical page.
        Labels do not carry across page breaks.
        """
        if not self._label_positions:
            return None

        page_number = self.page_at(char_offset)
        if page_number is None:
            return None

        current_page_start = 0
        if page_number > 1:
            current_page_start = self._page_break_positions[page_number - 2]

        idx = bisect.bisect_right(self._label_positions, char_offset) - 1
        if idx < 0:
            return None
        if self._label_positions[idx] < current_page_start:
            return None

        return self._labels[idx]

    @property
    def pages(self) -> list[tuple[int, int]]:
        """Get page label markers as (position, physical_page_number) tuples."""
        pages: list[tuple[int, int]] = []
        for pos in self._label_positions:
            page_number = self.page_at(pos)
            if page_number is None:
                continue
            pages.append((pos, page_number))
        return pages

    @property
    def page_labels(self) -> list[tuple[int, str]]:
        """Get valid page labels as (position, label) tuples."""
        return list(zip(self._label_positions, self._labels, strict=True))
