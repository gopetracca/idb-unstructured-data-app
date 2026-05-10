"""Unit tests for HTML table extraction handler."""

import pytest

from src.infrastructure.chonkie.table_handler import (
    TableBlock,
    extract_tables,
    get_placeholder_pattern,
)


class TestExtractTables:
    """Tests for extract_tables function."""

    def test_no_tables(self):
        """Text without tables returns unchanged."""
        text = "# Introduction\n\nSome paragraph text.\n\n## Section 2\n\nMore text."
        modified, tables = extract_tables(text)

        assert modified == text
        assert tables == []

    def test_single_table(self):
        """Single table is extracted and replaced with placeholder."""
        text = "Before table.\n\n<table><tr><td>A</td></tr></table>\n\nAfter table."
        modified, tables = extract_tables(text)

        assert len(tables) == 1
        assert tables[0].table_id == "table_0"
        assert tables[0].html == "<table><tr><td>A</td></tr></table>"
        assert "<!-- TABLE_PLACEHOLDER_0 -->" in modified
        assert "<table>" not in modified
        assert "Before table." in modified
        assert "After table." in modified

    def test_multiple_tables(self):
        """Multiple tables are extracted in order."""
        text = (
            "Text 1.\n\n"
            "<table><tr><td>Table A</td></tr></table>\n\n"
            "Text 2.\n\n"
            "<table><tr><td>Table B</td></tr></table>\n\n"
            "Text 3."
        )
        modified, tables = extract_tables(text)

        assert len(tables) == 2
        assert tables[0].table_id == "table_0"
        assert tables[1].table_id == "table_1"
        assert "Table A" in tables[0].html
        assert "Table B" in tables[1].html
        assert "<!-- TABLE_PLACEHOLDER_0 -->" in modified
        assert "<!-- TABLE_PLACEHOLDER_1 -->" in modified

    def test_back_to_back_tables(self):
        """Back-to-back tables without text between them."""
        text = (
            "<table><tr><td>A</td></tr></table>"
            "<table><tr><td>B</td></tr></table>"
        )
        modified, tables = extract_tables(text)

        assert len(tables) == 2
        assert "<!-- TABLE_PLACEHOLDER_0 -->" in modified
        assert "<!-- TABLE_PLACEHOLDER_1 -->" in modified

    def test_nested_tables(self):
        """Nested tables are captured as one outermost block."""
        text = (
            "Before.\n\n"
            "<table><tr><td><table><tr><td>Inner</td></tr></table></td></tr></table>"
            "\n\nAfter."
        )
        modified, tables = extract_tables(text)

        assert len(tables) == 1
        assert "Inner" in tables[0].html
        assert tables[0].html.startswith("<table>")
        assert tables[0].html.endswith("</table>")

    def test_table_with_attributes(self):
        """Tables with HTML attributes are handled."""
        text = '<table class="data" border="1"><tr><td>Cell</td></tr></table>'
        modified, tables = extract_tables(text)

        assert len(tables) == 1
        assert 'class="data"' in tables[0].html

    def test_table_preserves_positions(self):
        """Table start_index and end_index match original text positions."""
        prefix = "Prefix text.\n\n"
        table_html = "<table><tr><td>Data</td></tr></table>"
        suffix = "\n\nSuffix text."
        text = prefix + table_html + suffix

        _, tables = extract_tables(text)

        assert tables[0].start_index == len(prefix)
        assert tables[0].end_index == len(prefix) + len(table_html)

    def test_empty_text(self):
        """Empty text returns empty results."""
        modified, tables = extract_tables("")
        assert modified == ""
        assert tables == []

    def test_case_insensitive(self):
        """Table tags are case-insensitive."""
        text = "<TABLE><TR><TD>data</TD></TR></TABLE>"
        modified, tables = extract_tables(text)

        assert len(tables) == 1
        assert "<TABLE>" in tables[0].html


class TestPlaceholderPattern:
    """Tests for get_placeholder_pattern."""

    def test_matches_placeholder(self):
        """Pattern matches valid placeholders."""
        pattern = get_placeholder_pattern()
        text = "Some text <!-- TABLE_PLACEHOLDER_0 --> more text"
        match = pattern.search(text)

        assert match is not None
        assert match.group(1) == "0"

    def test_matches_multi_digit(self):
        """Pattern matches multi-digit placeholder indices."""
        pattern = get_placeholder_pattern()
        match = pattern.search("<!-- TABLE_PLACEHOLDER_12 -->")

        assert match is not None
        assert match.group(1) == "12"

    def test_no_match_on_regular_comment(self):
        """Pattern does not match regular HTML comments."""
        pattern = get_placeholder_pattern()
        match = pattern.search("<!-- some comment -->")

        assert match is None
