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

# Registry mapping document type -> type-specific fields
_DOCUMENT_TYPE_FIELDS: dict[str, tuple[IndexFieldSpec, ...]] = {
    "operational": OPERATIONAL_INDEX_FIELDS,
    "publication": PUBLICATION_INDEX_FIELDS,
}


def get_index_schema(document_type: str) -> tuple[IndexFieldSpec, ...]:
    """
    Get the complete index schema for a document type.

    Returns the combined schema of:
    - Common fields (all document types)
    - Chunk-level fields (all document types)
    - Document-type-specific fields

    Args:
        document_type: Type of document (e.g., "operational", "publication")

    Returns:
        Tuple of IndexFieldSpec defining all metadata fields for the index

    Raises:
        ValueError: If document_type is not registered

    Example:
        >>> schema = get_index_schema("operational")
        >>> field_names = [f.name for f in schema]
        >>> assert "operation_number" in field_names
        >>> assert "page_number" in field_names  # chunk field
        >>> assert "country" in field_names       # common field
    """
    if document_type not in _DOCUMENT_TYPE_FIELDS:
        available = ", ".join(sorted(_DOCUMENT_TYPE_FIELDS.keys()))
        raise ValueError(
            f"Unknown document type: '{document_type}'. Available types: {available}"
        )

    type_specific = _DOCUMENT_TYPE_FIELDS[document_type]
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


def get_type_specific_schema(document_type: str) -> tuple[IndexFieldSpec, ...]:
    """
    Get only the type-specific fields for a document type.

    Useful for understanding what fields are unique to a document type.

    Args:
        document_type: Type of document

    Returns:
        Tuple of IndexFieldSpec for type-specific fields only.

    Raises:
        ValueError: If document_type is not registered
    """
    if document_type not in _DOCUMENT_TYPE_FIELDS:
        available = ", ".join(sorted(_DOCUMENT_TYPE_FIELDS.keys()))
        raise ValueError(
            f"Unknown document type: '{document_type}'. Available types: {available}"
        )
    return _DOCUMENT_TYPE_FIELDS[document_type]


def list_document_types() -> list[str]:
    """Return list of registered document types."""
    return sorted(_DOCUMENT_TYPE_FIELDS.keys())


def get_field_by_name(document_type: str, field_name: str) -> IndexFieldSpec | None:
    """
    Get a specific field spec by name from a document type's schema.

    Args:
        document_type: Type of document
        field_name: Name of the field to find

    Returns:
        IndexFieldSpec if found, None otherwise
    """
    schema = get_index_schema(document_type)
    for field in schema:
        if field.name == field_name:
            return field
    return None


def get_filterable_fields(document_type: str) -> tuple[IndexFieldSpec, ...]:
    """
    Get all filterable fields for a document type.

    Useful for building filter UIs or validating filter parameters.

    Args:
        document_type: Type of document

    Returns:
        Tuple of IndexFieldSpec where filterable=True
    """
    schema = get_index_schema(document_type)
    return tuple(f for f in schema if f.filterable)


def get_sortable_fields(document_type: str) -> tuple[IndexFieldSpec, ...]:
    """
    Get all sortable fields for a document type.

    Useful for building sort UIs or validating sort parameters.

    Args:
        document_type: Type of document

    Returns:
        Tuple of IndexFieldSpec where sortable=True
    """
    schema = get_index_schema(document_type)
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
    "list_document_types",
    "get_field_by_name",
    "get_filterable_fields",
    "get_sortable_fields",
    # Field definitions (for direct access if needed)
    "COMMON_INDEX_FIELDS",
    "CHUNK_INDEX_FIELDS",
    "OPERATIONAL_INDEX_FIELDS",
    "PUBLICATION_INDEX_FIELDS",
]
