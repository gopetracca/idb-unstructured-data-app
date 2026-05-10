"""Search mode value object."""

from enum import StrEnum


class SearchMode(StrEnum):
    SEMANTIC = "semantic"
    KEYWORD = "keyword"
    HYBRID = "hybrid"
