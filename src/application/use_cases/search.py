"""Unified search use case supporting semantic, keyword, and hybrid modes."""

import logging
import time
from typing import Any

from src.application.dto.search_dto import SemanticSearchInput, SemanticSearchOutput
from src.application.ports.embedding import EmbeddingPort
from src.application.ports.vector_database import VectorDatabasePort
from src.core.entities.search_result import SearchResult
from src.core.errors import UnsupportedFilterError, ValidationError
from src.core.value_objects.search_mode import SearchMode

logger = logging.getLogger(__name__)

_collection_cache: dict[str, dict[str, Any]] = {}
_cache_max_size = 128


def _get_cached_collection_info(index_name: str) -> dict[str, Any] | None:
    return _collection_cache.get(index_name)


def _cache_collection_info(index_name: str, collection_info: dict[str, Any]) -> None:
    global _collection_cache
    if len(_collection_cache) >= _cache_max_size:
        first_key = next(iter(_collection_cache))
        del _collection_cache[first_key]
    _collection_cache[index_name] = collection_info


def clear_collection_cache(index_name: str | None = None) -> None:
    global _collection_cache
    if index_name:
        _collection_cache.pop(index_name, None)
    else:
        _collection_cache.clear()


class SearchUseCase:
    """
    Unified search use case supporting semantic (vector), keyword (BM25), and hybrid (RRF) modes.

    Responsibilities:
    - Generate query embedding only when the mode requires vectors (semantic/hybrid).
    - Pass query_text for BM25 in keyword/hybrid modes.
    - Delegate to VectorDatabasePort with the resolved mode and reranker flag.
    - Sort results by reranker_score (when present) or score.
    - Apply min_score filtering, sorting, and pagination.
    """

    def __init__(
        self,
        vector_database: VectorDatabasePort,
        embedding_port: EmbeddingPort,
    ) -> None:
        self._vector_database = vector_database
        self._embedding_port = embedding_port
        self._supported_filters = {
            "file_ids",
            "document_type",
            "tags",
            "department",
            "source",
            "operation_number",
            "sector",
            "country",
            "operation_type",
            "dept_id",
            "disclosed",
            "year",
            "year_min",
            "year_max",
            "document_author",
            "file_extension",
            "document_name",
            "ezshare_id",
            "document_publish_date_from",
            "document_publish_date_to",
        }
        self._supported_sort_fields = {
            "score",
            "year",
            "document_publish_date",
            "document_name",
            "operation_number",
            "country",
            "sector",
            "document_type",
            "department",
            "source",
        }

    async def execute(self, input_dto: SemanticSearchInput) -> SemanticSearchOutput:
        """Execute search with the requested mode."""
        start_time = time.time()

        logger.debug(
            "Executing %s search: query='%s...', index=%s, top_k=%d, reranker=%s, correlation_id=%s",
            input_dto.search_mode,
            input_dto.query[:50],
            input_dto.index_name,
            input_dto.top_k,
            input_dto.enable_reranker,
            input_dto.correlation_id,
        )

        # Fetch collection metadata (embedding model) — only needed for vector modes
        needs_vector = input_dto.search_mode in (SearchMode.SEMANTIC, SearchMode.HYBRID)

        collection_info = _get_cached_collection_info(input_dto.index_name)
        if collection_info is None:
            logger.debug("Collection cache miss for '%s', fetching from database", input_dto.index_name)
            collection_info = await self._vector_database.get_index(input_dto.index_name)
            _cache_collection_info(input_dto.index_name, collection_info)
        else:
            logger.debug("Collection cache hit for '%s'", input_dto.index_name)

        embedding_model = collection_info.get("embedding_model", "text-embedding-3-small")
        expected_vector_dimension = collection_info.get("vector_dimension")

        if input_dto.enable_reranker and not collection_info.get("reranker_enabled", False):
            raise ValidationError(
                message="Reranker is not configured for this collection. "
                "Enable it first via POST /collections/{name}/reranker.",
                field="enable_reranker",
                details={"index_name": input_dto.index_name},
            )

        # Generate query embedding only when required
        query_vector: list[float] | None = None
        if needs_vector:
            embedding_results = await self._embedding_port.generate_embeddings(
                texts=[input_dto.query],
                model=embedding_model,
            )
            query_vector = embedding_results[0].vector
            if isinstance(expected_vector_dimension, int) and expected_vector_dimension > 0:
                actual_dimension = len(query_vector)
                if actual_dimension != expected_vector_dimension:
                    raise ValidationError(
                        message=(
                            "Query vector dimension does not match index vector dimension"
                        ),
                        field="index_name",
                        details={
                            "index_name": input_dto.index_name,
                            "expected_vector_dimension": expected_vector_dimension,
                            "actual_query_vector_dimension": actual_dimension,
                            "embedding_model": embedding_model,
                        },
                    )
            logger.debug(
                "Generated query embedding: dimension=%d, model=%s",
                len(query_vector),
                embedding_model,
            )

        filters = self._build_filters(input_dto)
        logger.debug("Built filters: %s, correlation_id=%s", filters, input_dto.correlation_id)

        top_k = self._resolve_top_k(input_dto)
        search_results = await self._vector_database.search(
            index_name=input_dto.index_name,
            query_text=input_dto.query,
            query_vector=query_vector,
            top_k=top_k,
            filters=filters if filters else None,
            search_mode=input_dto.search_mode,
            enable_reranker=input_dto.enable_reranker,
            reranker_profile=input_dto.reranker_profile,
        )

        logger.debug(
            "Search completed: found=%d, correlation_id=%s",
            len(search_results),
            input_dto.correlation_id,
        )

        # Apply min_score filter against the primary ranking signal
        if input_dto.min_score > 0.0:
            before_count = len(search_results)
            search_results = [r for r in search_results if self._primary_score(r, input_dto.enable_reranker) >= input_dto.min_score]
            logger.debug(
                "Applied min_score filter: %d -> %d, min_score=%s",
                before_count,
                len(search_results),
                input_dto.min_score,
            )

        total_results = len(search_results)

        search_results = self._apply_sorting(
            search_results,
            input_dto.sort_by,
            input_dto.order,
            reranker_enabled=input_dto.enable_reranker,
        )
        search_results = self._apply_pagination(
            search_results,
            input_dto.page_size,
            input_dto.page_number,
        )

        search_time_ms = int((time.time() - start_time) * 1000)
        reranker_enabled = input_dto.enable_reranker and any(r.reranker_score is not None for r in search_results)

        logger.debug(
            "Search use case done: results=%d, time=%dms, correlation_id=%s",
            len(search_results),
            search_time_ms,
            input_dto.correlation_id,
        )

        return SemanticSearchOutput(
            query=input_dto.query,
            results=search_results,
            total_results=total_results,
            search_time_ms=search_time_ms,
            embedding_model=embedding_model,
            filters_applied=filters,
            search_mode=input_dto.search_mode,
            reranker_enabled=reranker_enabled,
            correlation_id=input_dto.correlation_id,
        )

    @staticmethod
    def _primary_score(result: SearchResult, reranker_enabled: bool) -> float:
        if reranker_enabled and result.reranker_score is not None:
            # Normalise reranker_score (0-4) to 0-1 for min_score comparison
            return result.reranker_score / 4.0
        return result.score

    def _build_filters(self, input_dto: SemanticSearchInput) -> dict[str, Any]:
        filters: dict[str, Any] = {}

        if input_dto.filters:
            filters.update(input_dto.filters)

        if input_dto.file_ids:
            filters["file_ids"] = input_dto.file_ids
        if input_dto.document_type:
            filters["document_type"] = input_dto.document_type
        if input_dto.tags:
            filters["tags"] = input_dto.tags
        if input_dto.department:
            filters["department"] = input_dto.department
        if input_dto.source:
            filters["source"] = input_dto.source
        if input_dto.operation_number:
            filters["operation_number"] = input_dto.operation_number
        if input_dto.sector:
            filters["sector"] = input_dto.sector
        if input_dto.country:
            filters["country"] = input_dto.country
        if input_dto.operation_type:
            filters["operation_type"] = input_dto.operation_type
        if input_dto.dept_id:
            filters["dept_id"] = input_dto.dept_id
        if input_dto.disclosed is not None:
            filters["disclosed"] = input_dto.disclosed
        if input_dto.year is not None:
            filters["year"] = input_dto.year
        if input_dto.year_min is not None:
            filters["year_min"] = input_dto.year_min
        if input_dto.year_max is not None:
            filters["year_max"] = input_dto.year_max
        if input_dto.document_author:
            filters["document_author"] = input_dto.document_author
        if input_dto.file_extension:
            filters["file_extension"] = input_dto.file_extension
        if input_dto.document_name:
            filters["document_name"] = input_dto.document_name
        if input_dto.ezshare_id:
            filters["ezshare_id"] = input_dto.ezshare_id
        if input_dto.document_publish_date_from:
            filters["document_publish_date_from"] = input_dto.document_publish_date_from
        if input_dto.document_publish_date_to:
            filters["document_publish_date_to"] = input_dto.document_publish_date_to

        filters = self._prune_filters(filters)
        self._validate_filters(filters)
        return filters

    def _prune_filters(self, filters: dict[str, Any]) -> dict[str, Any]:
        pruned: dict[str, Any] = {}
        for key, value in filters.items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            if isinstance(value, list) and len(value) == 0:
                continue
            pruned[key] = value
        return pruned

    def _validate_filters(self, filters: dict[str, Any]) -> None:
        if not filters:
            return
        unsupported = [key for key in filters if key not in self._supported_filters]
        if unsupported:
            raise UnsupportedFilterError(
                unsupported_filters=unsupported,
                supported_filters=sorted(self._supported_filters),
                details={
                    "unsupported_filters": sorted(unsupported),
                    "supported_filters": sorted(self._supported_filters),
                },
            )

    def _resolve_top_k(self, input_dto: SemanticSearchInput) -> int:
        if input_dto.page_size is None and input_dto.page_number is None:
            return input_dto.top_k

        page_size = input_dto.page_size or min(input_dto.top_k, 100)
        page_number = input_dto.page_number or 1

        max_items = 100
        effective_top_k = page_size * page_number
        if effective_top_k > max_items:
            raise ValidationError(
                message=f"Requested page exceeds maximum of {max_items} items",
                field="page_size",
                details={
                    "page_size": page_size,
                    "page_number": page_number,
                    "max_items": max_items,
                },
            )
        return effective_top_k

    def _apply_sorting(
        self,
        results: list[SearchResult],
        sort_by: str | None,
        order: str | None,
        reranker_enabled: bool,
    ) -> list[SearchResult]:
        if order and not sort_by:
            raise ValidationError(message="Sort order requires sort_by to be set", field="order")

        if not sort_by:
            return results

        sort_value = str(sort_by)
        if sort_value not in self._supported_sort_fields:
            raise ValidationError(
                message=f"Unsupported sort field: {sort_value}",
                field="sort_by",
                details={"supported_sort_fields": sorted(self._supported_sort_fields)},
            )

        reverse = str(order or "desc") == "desc"

        def sort_key(result: SearchResult) -> Any:
            if sort_value == "score":
                return (False, self._primary_score(result, reranker_enabled))
            value = getattr(result.metadata, sort_value, None)
            return (value is None, value)

        return sorted(results, key=sort_key, reverse=reverse)

    def _apply_pagination(
        self,
        results: list[SearchResult],
        page_size: int | None,
        page_number: int | None,
    ) -> list[SearchResult]:
        if page_size is None and page_number is None:
            return results

        resolved_page_size = page_size or 10
        resolved_page_number = page_number or 1

        start = (resolved_page_number - 1) * resolved_page_size
        end = start + resolved_page_size
        return results[start:end]
