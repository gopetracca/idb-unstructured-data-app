"""Index field specification — infrastructure-agnostic.

Defines the IndexFieldSpec dataclass used to declaratively specify metadata
fields that should be indexed. Uses a generic FieldType enum so the core
layer has no dependency on any specific search backend.

Conversion to backend-specific field objects (e.g. Azure SearchField) is
handled by infrastructure mappers:
    src.infrastructure.azure.adapters.index_schema_mapper
"""

from dataclasses import dataclass
from enum import Enum


class FieldType(Enum):
    """Generic field types, independent of any search backend."""

    STRING = "string"
    INT32 = "int32"
    BOOLEAN = "boolean"
    DATETIME = "datetime"


class FieldCategory(Enum):
    """Category of the index field for documentation purposes."""

    COMMON = "common"
    CHUNK = "chunk"
    DOCUMENT_TYPE = "doc_type"


@dataclass(frozen=True)
class IndexFieldSpec:
    """
    Declarative specification for a metadata field in a search index.

    Backend-agnostic: no dependency on any search SDK. Conversion to
    backend-specific field objects is the responsibility of infrastructure
    mappers, not this class.

    Attributes:
        name: Field name in the index (should match SearchableMetadata attribute)
        field_type: Generic field type (FieldType enum)
        filterable: Whether the field can be used in filter expressions
        sortable: Whether the field can be used in sort expressions
        facetable: Whether the field can be used for faceted navigation
        is_collection: Whether this is a multi-value (collection) field
        category: Categorization for documentation/organization
        description: Human-readable description of the field's purpose

    Example:
        >>> spec = IndexFieldSpec(
        ...     name="operation_number",
        ...     field_type=FieldType.STRING,
        ...     filterable=True,
        ...     sortable=True,
        ...     category=FieldCategory.DOCUMENT_TYPE,
        ...     description="IDB operation identifier (e.g., UR-L1234)"
        ... )
    """

    name: str
    field_type: FieldType
    filterable: bool = False
    sortable: bool = False
    facetable: bool = False
    is_collection: bool = False
    category: FieldCategory = FieldCategory.COMMON
    description: str = ""

    def __post_init__(self) -> None:
        """Validate field specification."""
        if (self.sortable or self.facetable) and not self.filterable:
            raise ValueError(
                f"Field '{self.name}': sortable/facetable requires filterable=True"
            )
        if self.sortable and self.is_collection:
            raise ValueError(f"Field '{self.name}': collections cannot be sortable")
