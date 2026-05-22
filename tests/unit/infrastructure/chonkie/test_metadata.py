"""Unit tests for metadata helpers: section path tracking, page tracking, and token counting."""

import pytest

import tiktoken

from src.infrastructure.chonkie.metadata import (
    HeadingTracker,
    PageTracker,
    count_tokens,
    get_tiktoken_encoding,
)


class TestGetTiktokenEncoding:
    """Tests for get_tiktoken_encoding function."""

    def test_returns_tiktoken_encoding(self):
        """Returns a tiktoken.Encoding instance."""
        enc = get_tiktoken_encoding()
        assert isinstance(enc, tiktoken.Encoding)

    def test_default_encoding_is_cl100k_base(self):
        """Default encoding is cl100k_base."""
        enc = get_tiktoken_encoding()
        assert enc.name == "cl100k_base"

    def test_returns_same_instance(self):
        """Multiple calls with the same name return the same cached instance."""
        enc1 = get_tiktoken_encoding("cl100k_base")
        enc2 = get_tiktoken_encoding("cl100k_base")
        assert enc1 is enc2

    def test_encoding_encodes_text(self):
        """Returned encoding can encode text."""
        enc = get_tiktoken_encoding()
        tokens = enc.encode("Hello, world!")
        assert len(tokens) > 0


class TestCountTokens:
    """Tests for count_tokens function."""

    def test_empty_string(self):
        """Empty string returns 0 tokens."""
        assert count_tokens("") == 0

    def test_simple_text(self):
        """Simple text returns positive token count."""
        result = count_tokens("Hello, world!")
        assert result > 0

    def test_longer_text_has_more_tokens(self):
        """Longer text has more tokens than shorter text."""
        short = count_tokens("Hello")
        long = count_tokens("Hello, this is a much longer piece of text with many more words.")
        assert long > short

    def test_consistent_results(self):
        """Same text always returns same token count."""
        text = "The quick brown fox jumps over the lazy dog."
        assert count_tokens(text) == count_tokens(text)


class TestHeadingTracker:
    """Tests for HeadingTracker class."""

    def test_no_headings(self):
        """Text without headings returns empty section path."""
        tracker = HeadingTracker("Just a plain paragraph without any headings.")
        assert tracker.section_path_at(0) == []
        assert tracker.section_path_at(20) == []

    def test_single_heading(self):
        """Single heading is tracked correctly."""
        text = "# Introduction\n\nSome text here."
        tracker = HeadingTracker(text)

        # Before heading
        assert tracker.section_path_at(0) == ["Introduction"]

        # After heading
        assert tracker.section_path_at(20) == ["Introduction"]

    def test_nested_headings(self):
        """Nested headings build proper hierarchy."""
        text = (
            "# Chapter 1\n\n"
            "## Section A\n\n"
            "Text in section A.\n\n"
            "## Section B\n\n"
            "Text in section B.\n\n"
            "### Subsection B1\n\n"
            "Text in subsection B1."
        )
        tracker = HeadingTracker(text)

        # After "# Chapter 1"
        path_ch1 = tracker.section_path_at(5)
        assert path_ch1 == ["Chapter 1"]

        # After "## Section A"
        path_a = tracker.section_path_at(30)
        assert path_a == ["Chapter 1", "Section A"]

        # After "## Section B"
        sec_b_pos = text.index("## Section B")
        path_b = tracker.section_path_at(sec_b_pos + 15)
        assert path_b == ["Chapter 1", "Section B"]

        # After "### Subsection B1"
        sub_b1_pos = text.index("### Subsection B1")
        path_b1 = tracker.section_path_at(sub_b1_pos + 20)
        assert path_b1 == ["Chapter 1", "Section B", "Subsection B1"]

    def test_heading_same_level_resets(self):
        """Same-level heading replaces previous heading at that level."""
        text = "## First\n\nText 1.\n\n## Second\n\nText 2."
        tracker = HeadingTracker(text)

        first_pos = text.index("Text 1.")
        assert tracker.section_path_at(first_pos) == ["First"]

        second_pos = text.index("Text 2.")
        assert tracker.section_path_at(second_pos) == ["Second"]

    def test_deep_heading_levels(self):
        """All 6 heading levels are supported."""
        text = (
            "# H1\n"
            "## H2\n"
            "### H3\n"
            "#### H4\n"
            "##### H5\n"
            "###### H6\n"
            "Content."
        )
        tracker = HeadingTracker(text)

        content_pos = text.index("Content.")
        path = tracker.section_path_at(content_pos)
        assert path == ["H1", "H2", "H3", "H4", "H5", "H6"]

    def test_heading_before_offset(self):
        """Only headings before the offset are included."""
        text = "# First\n\nMiddle text.\n\n# Second\n\nEnd text."
        tracker = HeadingTracker(text)

        middle_pos = text.index("Middle text.")
        assert tracker.section_path_at(middle_pos) == ["First"]

    def test_empty_text(self):
        """Empty text produces no headings."""
        tracker = HeadingTracker("")
        assert tracker.section_path_at(0) == []

    def test_headings_property(self):
        """Headings property returns parsed headings."""
        text = "# Title\n\n## Subtitle\n\nContent."
        tracker = HeadingTracker(text)

        headings = tracker.headings
        assert len(headings) == 2
        assert headings[0][1] == 1  # level
        assert headings[0][2] == "Title"
        assert headings[1][1] == 2
        assert headings[1][2] == "Subtitle"

    def test_heading_with_extra_whitespace(self):
        """Headings with trailing whitespace are trimmed."""
        text = "#  Padded Heading  \n\nContent."
        tracker = HeadingTracker(text)

        assert tracker.section_path_at(25) == ["Padded Heading"]

    def test_non_heading_hash(self):
        """Lines that look like headings but aren't (e.g., code) are handled gracefully."""
        text = "Some code:\n\n    # This is a comment\n\nMore text."
        tracker = HeadingTracker(text)

        # The indented # should not be matched as heading (it starts with spaces)
        assert tracker.section_path_at(40) == []


class TestPageTracker:
    """Tests for PageTracker class."""

    def test_no_page_markers(self):
        """Text without page structure returns None."""
        tracker = PageTracker("Just a plain paragraph without any page markers.")
        assert tracker.page_at(0) is None
        assert tracker.page_at(20) is None
        assert tracker.page_label_at(20) is None

    def test_empty_text(self):
        """Empty text returns None."""
        tracker = PageTracker("")
        assert tracker.page_at(0) is None
        assert tracker.page_label_at(0) is None

    def test_single_page_marker(self):
        """Single page marker gives physical page 1 and label 1."""
        text = 'Some text before.\n\n<!-- PageNumber="1" -->\n\nContent on page 1.'
        tracker = PageTracker(text)

        # Physical page is inferred from existing page structure
        assert tracker.page_at(0) == 1

        content_pos = text.index("Content on page 1.")
        assert tracker.page_at(content_pos) == 1
        assert tracker.page_label_at(content_pos) == "1"

    def test_multiple_page_markers(self):
        """Multiple pages are inferred from page breaks and labels are page-local."""
        text = (
            '<!-- PageNumber="1" -->\n\n'
            "Page 1 content.\n\n"
            "<!-- PageBreak -->\n\n"
            '<!-- PageNumber="2" -->\n\n'
            "Page 2 content.\n\n"
            "<!-- PageBreak -->\n\n"
            '<!-- PageNumber="3" -->\n\n'
            "Page 3 content."
        )
        tracker = PageTracker(text)

        p1_content = text.index("Page 1 content.")
        assert tracker.page_at(p1_content) == 1
        assert tracker.page_label_at(p1_content) == "1"

        p2_content = text.index("Page 2 content.")
        assert tracker.page_at(p2_content) == 2
        assert tracker.page_label_at(p2_content) == "2"

        p3_content = text.index("Page 3 content.")
        assert tracker.page_at(p3_content) == 3
        assert tracker.page_label_at(p3_content) == "3"

    def test_non_sequential_labels_keep_physical_order(self):
        """Printed labels can be non-sequential while physical pages stay monotonic."""
        text = (
            '<!-- PageNumber="47" -->\n\n'
            "Content on page 47.\n\n"
            "<!-- PageBreak -->\n\n"
            '<!-- PageNumber="48" -->\n\n'
            "Content on page 48."
        )
        tracker = PageTracker(text)

        p47 = text.index("Content on page 47.")
        assert tracker.page_at(p47) == 1
        assert tracker.page_label_at(p47) == "47"

        p48 = text.index("Content on page 48.")
        assert tracker.page_at(p48) == 2
        assert tracker.page_label_at(p48) == "48"

    def test_offset_before_first_marker(self):
        """Offset before first marker is still page 1 when structure exists."""
        text = (
            "Preamble text.\n\n"
            '<!-- PageNumber="5" -->\n<!-- PageBreak -->\n\n'
            "Page 5 content."
        )
        tracker = PageTracker(text)

        assert tracker.page_at(0) == 1
        assert tracker.page_at(10) == 1
        assert tracker.page_label_at(0) is None

    def test_pages_property(self):
        """Pages property returns marker positions with physical page numbers."""
        text = (
            '<!-- PageNumber="10" -->\n'
            "<!-- PageBreak -->\n"
            "Content.\n"
            '<!-- PageNumber="11" -->\n'
            "More content."
        )
        tracker = PageTracker(text)

        pages = tracker.pages
        assert len(pages) == 2
        assert pages[0][1] == 1
        assert pages[1][1] == 2

    def test_page_marker_with_table_content(self):
        """Page markers work correctly alongside HTML table content."""
        text = (
            '<!-- PageNumber="47" -->\n\n'
            "<table>\n<tr><td>Data</td></tr>\n</table>\n\n"
            "<!-- PageBreak -->\n\n"
            '<!-- PageNumber="48" -->\n\n'
            "Text after table."
        )
        tracker = PageTracker(text)

        table_pos = text.index("<table>")
        assert tracker.page_at(table_pos) == 1
        assert tracker.page_label_at(table_pos) == "47"

        after_pos = text.index("Text after table.")
        assert tracker.page_at(after_pos) == 2
        assert tracker.page_label_at(after_pos) == "48"

    def test_dashed_numeric_page_marker(self):
        """Dash-wrapped numeric labels are normalized."""
        text = (
            "Page 1 content.\n\n"
            "<!-- PageBreak -->\n\n"
            '<!-- PageNumber="- 2 -" -->\n\n'
            "Content on page 2."
        )
        tracker = PageTracker(text)

        content_pos = text.index("Content on page 2.")
        assert tracker.page_at(content_pos) == 2
        assert tracker.page_label_at(content_pos) == "2"

    def test_dashed_roman_page_marker(self):
        """Dash-wrapped roman labels are normalized."""
        text = (
            "Page 1 content.\n\n"
            "<!-- PageBreak -->\n\n"
            '<!-- PageNumber="- IV -" -->\n\n'
            "Content on page IV."
        )
        tracker = PageTracker(text)

        content_pos = text.index("Content on page IV.")
        assert tracker.page_at(content_pos) == 2
        assert tracker.page_label_at(content_pos) == "IV"

    def test_non_numeric_page_marker_is_preserved(self):
        """Non-numeric labels are preserved as-is in page_label."""
        text = (
            "Page 1 content.\n\n"
            "<!-- PageBreak -->\n\n"
            '<!-- PageNumber="- unknown -" -->\n\n'
            "Content after invalid marker."
        )
        tracker = PageTracker(text)

        content_pos = text.index("Content after invalid marker.")
        assert tracker.page_at(content_pos) == 2
        assert tracker.page_label_at(content_pos) == "unknown"

    def test_pagebreak_only_markdown_infers_physical_pages(self):
        """PageBreak-only markdown still resolves physical pages."""
        text = "First page content.\n\n<!-- PageBreak -->\n\nSecond page content."
        tracker = PageTracker(text)

        first_pos = text.index("First page content.")
        second_pos = text.index("Second page content.")
        assert tracker.page_at(first_pos) == 1
        assert tracker.page_at(second_pos) == 2
        assert tracker.page_label_at(first_pos) is None
        assert tracker.page_label_at(second_pos) is None

    def test_missing_label_on_page_returns_none_label(self):
        """A page without PageNumber has no label, even if neighbors do."""
        text = (
            '<!-- PageNumber="i" -->\n\n'
            "Front matter page.\n\n"
            "<!-- PageBreak -->\n\n"
            "Unlabeled page.\n\n"
            "<!-- PageBreak -->\n\n"
            '<!-- PageNumber="1" -->\n\n'
            "Body page."
        )
        tracker = PageTracker(text)

        unlabeled_pos = text.index("Unlabeled page.")
        body_pos = text.index("Body page.")
        assert tracker.page_at(unlabeled_pos) == 2
        assert tracker.page_label_at(unlabeled_pos) is None
        assert tracker.page_at(body_pos) == 3
        assert tracker.page_label_at(body_pos) == "1"

    def test_mixed_roman_and_arabic_labels_keep_monotonic_page_numbers(self):
        """Mixed labels map to physical pages while preserving printed labels."""
        text = (
            '<!-- PageNumber="i" -->\n\n'
            "Page i.\n\n"
            "<!-- PageBreak -->\n\n"
            '<!-- PageNumber="ii" -->\n\n'
            "Page ii.\n\n"
            "<!-- PageBreak -->\n\n"
            '<!-- PageNumber="iii" -->\n\n'
            "Page iii.\n\n"
            "<!-- PageBreak -->\n\n"
            '<!-- PageNumber="1" -->\n\n'
            "Page 1.\n\n"
            "<!-- PageBreak -->\n\n"
            '<!-- PageNumber="2" -->\n\n'
            "Page 2."
        )
        tracker = PageTracker(text)

        positions = [
            text.index("Page i."),
            text.index("Page ii."),
            text.index("Page iii."),
            text.index("Page 1."),
            text.index("Page 2."),
        ]
        labels = ["i", "ii", "iii", "1", "2"]

        for idx, pos in enumerate(positions, start=1):
            assert tracker.page_at(pos) == idx
            assert tracker.page_label_at(pos) == labels[idx - 1]
