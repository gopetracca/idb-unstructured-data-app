"""
Index Schema Registry for Azure AI Search.

This module provides declarative schema definitions for different document types.
Each document type has its own set of indexed metadata fields, enabling:
- Per-document-type indexes with optimized schemas
- Clear separation between common and type-specific fields
- Easy extension for new document types

Usage:
    >>> from src.core.index_schemas import get_index_schema, list_document_types
    >>>
    >>> # Get schema for operational documents
    >>> schema = get_index_schema("operational")
    >>> for field in schema:
    ...     print(f"{field.name}: {field.field_type}")
    >>>
    >>> # List available document types
    >>> print(list_document_types())  # ['operational', 'publication']
"""

from src.core.index_schemas.field_spec import FieldCategory, FieldType, IndexFieldSpec
from src.core.index_schemas.common_fields import COMMON_INDEX_FIELDS
from src.core.index_schemas.chunk_fields import CHUNK_INDEX_FIELDS
from src.core.index_schemas.document_types.operational import OPERATIONAL_INDEX_FIELDS
from src.core.index_schemas.document_types.publication import PUBLICATION_INDEX_FIELDS


# Base fields included in every index (common + chunk)
_BASE_FIELDS: tuple[IndexFieldSpec, ...] = COMMON_INDEX_FIELDS + CHUNK_INDEX_FIELDS

# Registry mapping document category -> category-specific fields
_DOCUMENT_CATEGORY_FIELDS: dict[str, tuple[IndexFieldSpec, ...]] = {
    "operational": OPERATIONAL_INDEX_FIELDS,
    "publication": PUBLICATION_INDEX_FIELDS,
}

# Backward-compatible alias
_DOCUMENT_TYPE_FIELDS = _DOCUMENT_CATEGORY_FIELDS


def get_index_schema(document_category: str) -> tuple[IndexFieldSpec, ...]:
    """
    Get the complete index schema for a document category.

    Returns the combined schema of:
    - Common fields (all document categories)
    - Chunk-level fields (all document categories)
    - Category-specific fields

    Args:
        document_category: Category of document (e.g., "operational", "publication")

    Returns:
        Tuple of IndexFieldSpec defining all metadata fields for the index

    Raises:
        ValueError: If document_category is not registered

    Example:
        >>> schema = get_index_schema("operational")
        >>> field_names = [f.name for f in schema]
        >>> assert "operation_number" in field_names
        >>> assert "page_number" in field_names  # chunk field
        >>> assert "country" in field_names       # common field
    """
    if document_category not in _DOCUMENT_CATEGORY_FIELDS:
        available = ", ".join(sorted(_DOCUMENT_CATEGORY_FIELDS.keys()))
        raise ValueError(
            f"Unknown document category: '{document_category}'. Available categories: {available}"
        )

    type_specific = _DOCUMENT_CATEGORY_FIELDS[document_category]
    return _BASE_FIELDS + type_specific


def get_base_schema() -> tuple[IndexFieldSpec, ...]:
    """
    Get only the base schema (common + chunk fields).

    Useful for creating a minimal index without document-type-specific fields,
    or for understanding what fields are shared across all document types.

    Returns:
        Tuple of IndexFieldSpec for common and chunk fields only.
    """
    return _BASE_FIELDS


def get_type_specific_schema(document_category: str) -> tuple[IndexFieldSpec, ...]:
    """
    Get only the category-specific fields for a document category.

    Useful for understanding what fields are unique to a document category.

    Args:
        document_category: Category of document

    Returns:
        Tuple of IndexFieldSpec for category-specific fields only.

    Raises:
        ValueError: If document_category is not registered
    """
    if document_category not in _DOCUMENT_CATEGORY_FIELDS:
        available = ", ".join(sorted(_DOCUMENT_CATEGORY_FIELDS.keys()))
        raise ValueError(
            f"Unknown document category: '{document_category}'. Available categories: {available}"
        )
    return _DOCUMENT_CATEGORY_FIELDS[document_category]


def list_document_categories() -> list[str]:
    """Return list of registered document categories."""
    return sorted(_DOCUMENT_CATEGORY_FIELDS.keys())


def list_document_types() -> list[str]:
    """Return list of registered document categories (alias for backward compatibility)."""
    return list_document_categories()


def get_field_by_name(document_category: str, field_name: str) -> IndexFieldSpec | None:
    """
    Get a specific field spec by name from a document category's schema.

    Args:
        document_category: Category of document
        field_name: Name of the field to find

    Returns:
        IndexFieldSpec if found, None otherwise
    """
    schema = get_index_schema(document_category)
    for field in schema:
        if field.name == field_name:
            return field
    return None


def get_filterable_fields(document_category: str) -> tuple[IndexFieldSpec, ...]:
    """
    Get all filterable fields for a document category.

    Useful for building filter UIs or validating filter parameters.

    Args:
        document_category: Category of document

    Returns:
        Tuple of IndexFieldSpec where filterable=True
    """
    schema = get_index_schema(document_category)
    return tuple(f for f in schema if f.filterable)


def get_sortable_fields(document_category: str) -> tuple[IndexFieldSpec, ...]:
    """
    Get all sortable fields for a document category.

    Useful for building sort UIs or validating sort parameters.

    Args:
        document_category: Category of document

    Returns:
        Tuple of IndexFieldSpec where sortable=True
    """
    schema = get_index_schema(document_category)
    return tuple(f for f in schema if f.sortable)


# Public API
__all__ = [
    # Core types
    "IndexFieldSpec",
    "FieldCategory",
    "FieldType",
    # Schema getters
    "get_index_schema",
    "get_base_schema",
    "get_type_specific_schema",
    "list_document_categories",
    "list_document_types",  # backward-compatible alias
    "get_field_by_name",
    "get_filterable_fields",
    "get_sortable_fields",
    # Field definitions (for direct access if needed)
    "COMMON_INDEX_FIELDS",
    "CHUNK_INDEX_FIELDS",
    "OPERATIONAL_INDEX_FIELDS",
    "PUBLICATION_INDEX_FIELDS",
]
