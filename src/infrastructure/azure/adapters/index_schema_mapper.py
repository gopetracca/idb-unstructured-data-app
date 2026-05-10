"""Azure AI Search mapper for IndexFieldSpec.

This module is the single place that knows both the generic IndexFieldSpec
(core) and the Azure Search SDK types (infrastructure). It converts a
FieldType/IndexFieldSpec into the concrete Azure SearchField objects needed
to build an index schema.
"""

from azure.search.documents.indexes.models import (
    SearchField,
    SearchFieldDataType,
    SimpleField,
)

from src.core.index_schemas.field_spec import FieldType, IndexFieldSpec

_FIELD_TYPE_MAP: dict[FieldType, SearchFieldDataType] = {
    FieldType.STRING: SearchFieldDataType.String,
    FieldType.INT32: SearchFieldDataType.Int32,
    FieldType.BOOLEAN: SearchFieldDataType.Boolean,
    FieldType.DATETIME: SearchFieldDataType.DateTimeOffset,
}


def to_azure_search_field(spec: IndexFieldSpec) -> SearchField:
    """Convert a generic IndexFieldSpec to an Azure AI Search field.

    Args:
        spec: The backend-agnostic field specification.

    Returns:
        An Azure SearchField ready to be included in a SearchIndex schema.

    Raises:
        ValueError: If spec.field_type is not mapped.
    """
    azure_type = _FIELD_TYPE_MAP.get(spec.field_type)
    if azure_type is None:
        raise ValueError(
            f"Field '{spec.name}': unsupported FieldType '{spec.field_type}'"
        )

    if spec.is_collection:
        return SearchField(
            name=spec.name,
            type=SearchFieldDataType.Collection(azure_type),
            filterable=spec.filterable,
            sortable=False,
            facetable=spec.facetable,
        )

    return SimpleField(
        name=spec.name,
        type=azure_type,
        filterable=spec.filterable,
        sortable=spec.sortable,
        facetable=spec.facetable,
    )
