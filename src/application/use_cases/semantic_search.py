"""Backward-compatible re-export; use SearchUseCase from search.py directly."""

from src.application.use_cases.search import (
    SearchUseCase,
    clear_collection_cache,
)

# Alias kept so existing imports of SemanticSearchUseCase continue to work.
SemanticSearchUseCase = SearchUseCase

__all__ = ["SemanticSearchUseCase", "SearchUseCase", "clear_collection_cache"]
