"""Unit tests for the Azure index schema mapper."""

import pytest
from azure.search.documents.indexes.models import SearchField, SearchFieldDataType

from src.core.index_schemas.field_spec import FieldCategory, FieldType, IndexFieldSpec
from src.infrastructure.azure.adapters.index_schema_mapper import to_azure_search_field


class TestToAzureSearchField:
    """Tests for to_azure_search_field()."""

    def test_string_field(self):
        """STRING maps to SearchFieldDataType.String."""
        spec = IndexFieldSpec(name="country", field_type=FieldType.STRING, filterable=True)
        field = to_azure_search_field(spec)

        assert isinstance(field, SearchField)
        assert field.name == "country"
        assert field.type == SearchFieldDataType.String
        assert field.filterable is True

    def test_int32_field(self):
        """INT32 maps to SearchFieldDataType.Int32."""
        spec = IndexFieldSpec(
            name="year", field_type=FieldType.INT32, filterable=True, sortable=True
        )
        field = to_azure_search_field(spec)

        assert field.name == "year"
        assert field.type == SearchFieldDataType.Int32
        assert field.sortable is True

    def test_boolean_field(self):
        """BOOLEAN maps to SearchFieldDataType.Boolean."""
        spec = IndexFieldSpec(name="disclosed", field_type=FieldType.BOOLEAN, filterable=True)
        field = to_azure_search_field(spec)

        assert field.name == "disclosed"
        assert field.type == SearchFieldDataType.Boolean

    def test_datetime_field(self):
        """DATETIME maps to SearchFieldDataType.DateTimeOffset."""
        spec = IndexFieldSpec(
            name="document_publish_date",
            field_type=FieldType.DATETIME,
            filterable=True,
            sortable=True,
        )
        field = to_azure_search_field(spec)

        assert field.name == "document_publish_date"
        assert field.type == SearchFieldDataType.DateTimeOffset
        assert field.sortable is True

    def test_collection_field(self):
        """is_collection=True produces Collection(String) type."""
        spec = IndexFieldSpec(
            name="tags",
            field_type=FieldType.STRING,
            filterable=True,
            is_collection=True,
        )
        field = to_azure_search_field(spec)

        assert field.name == "tags"
        assert field.type == SearchFieldDataType.Collection(SearchFieldDataType.String)
        assert field.filterable is True
        assert field.sortable is False  # collections cannot be sorted

    def test_collection_is_never_sortable(self):
        """Collection fields have sortable=False regardless of spec."""
        spec = IndexFieldSpec(
            name="tags",
            field_type=FieldType.STRING,
            filterable=True,
            is_collection=True,
        )
        field = to_azure_search_field(spec)

        assert field.sortable is False

    def test_non_filterable_field(self):
        """Non-filterable fields have filterable=False."""
        spec = IndexFieldSpec(name="blob_name", field_type=FieldType.STRING, filterable=False)
        field = to_azure_search_field(spec)

        assert field.filterable is False

    def test_facetable_field(self):
        """Facetable flag is passed through."""
        spec = IndexFieldSpec(
            name="sector",
            field_type=FieldType.STRING,
            filterable=True,
            facetable=True,
        )
        field = to_azure_search_field(spec)

        assert field.facetable is True

    def test_all_field_types_are_mapped(self):
        """Every FieldType value produces a valid SearchField."""
        for ft in FieldType:
            spec = IndexFieldSpec(name="test", field_type=ft)
            field = to_azure_search_field(spec)
            assert isinstance(field, SearchField)
