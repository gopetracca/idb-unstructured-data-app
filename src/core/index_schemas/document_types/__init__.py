"""Document type-specific index field definitions."""

from src.core.index_schemas.document_types.operational import OPERATIONAL_INDEX_FIELDS
from src.core.index_schemas.document_types.publication import PUBLICATION_INDEX_FIELDS

__all__ = [
    "OPERATIONAL_INDEX_FIELDS",
    "PUBLICATION_INDEX_FIELDS",
]
