"""Unit tests for IndexFieldSpec dataclass."""

import pytest

from src.core.index_schemas.field_spec import FieldCategory, FieldType, IndexFieldSpec


class TestIndexFieldSpec:
    """Tests for IndexFieldSpec dataclass."""

    def test_create_basic_field(self):
        """Test creating a basic field specification."""
        spec = IndexFieldSpec(
            name="country",
            field_type=FieldType.STRING,
            filterable=True,
            category=FieldCategory.COMMON,
            description="Country code",
        )

        assert spec.name == "country"
        assert spec.field_type == FieldType.STRING
        assert spec.filterable is True
        assert spec.sortable is False
        assert spec.facetable is False
        assert spec.is_collection is False
        assert spec.category == FieldCategory.COMMON
        assert spec.description == "Country code"

    def test_create_sortable_field(self):
        """Test creating a sortable field (requires filterable)."""
        spec = IndexFieldSpec(
            name="year",
            field_type=FieldType.INT32,
            filterable=True,
            sortable=True,
            category=FieldCategory.COMMON,
        )

        assert spec.sortable is True
        assert spec.filterable is True

    def test_create_facetable_field(self):
        """Test creating a facetable field (requires filterable)."""
        spec = IndexFieldSpec(
            name="sector",
            field_type=FieldType.STRING,
            filterable=True,
            facetable=True,
            category=FieldCategory.DOCUMENT_TYPE,
        )

        assert spec.facetable is True
        assert spec.filterable is True

    def test_create_collection_field(self):
        """Test creating a collection field."""
        spec = IndexFieldSpec(
            name="tags",
            field_type=FieldType.STRING,
            filterable=True,
            is_collection=True,
            category=FieldCategory.COMMON,
        )

        assert spec.is_collection is True
        assert spec.sortable is False  # Collections cannot be sortable

    def test_create_boolean_field(self):
        """Test creating a boolean field."""
        spec = IndexFieldSpec(
            name="disclosed",
            field_type=FieldType.BOOLEAN,
            filterable=True,
        )
        assert spec.field_type == FieldType.BOOLEAN

    def test_create_datetime_field(self):
        """Test creating a datetime field."""
        spec = IndexFieldSpec(
            name="document_publish_date",
            field_type=FieldType.DATETIME,
            filterable=True,
            sortable=True,
        )
        assert spec.field_type == FieldType.DATETIME

    def test_sortable_requires_filterable(self):
        """Test that sortable fields must be filterable."""
        with pytest.raises(ValueError, match="sortable/facetable requires filterable=True"):
            IndexFieldSpec(
                name="invalid",
                field_type=FieldType.STRING,
                filterable=False,
                sortable=True,
            )

    def test_facetable_requires_filterable(self):
        """Test that facetable fields must be filterable."""
        with pytest.raises(ValueError, match="sortable/facetable requires filterable=True"):
            IndexFieldSpec(
                name="invalid",
                field_type=FieldType.STRING,
                filterable=False,
                facetable=True,
            )

    def test_collection_cannot_be_sortable(self):
        """Test that collection fields cannot be sortable."""
        with pytest.raises(ValueError, match="collections cannot be sortable"):
            IndexFieldSpec(
                name="invalid",
                field_type=FieldType.STRING,
                filterable=True,
                sortable=True,
                is_collection=True,
            )

    def test_frozen_immutability(self):
        """Test that IndexFieldSpec is immutable (frozen dataclass)."""
        spec = IndexFieldSpec(
            name="test",
            field_type=FieldType.STRING,
        )

        with pytest.raises(AttributeError):
            spec.name = "changed"  # type: ignore


class TestFieldType:
    """Tests for FieldType enum."""

    def test_all_types_exist(self):
        """Test that all expected types exist."""
        assert FieldType.STRING.value == "string"
        assert FieldType.INT32.value == "int32"
        assert FieldType.BOOLEAN.value == "boolean"
        assert FieldType.DATETIME.value == "datetime"

    def test_field_type_in_spec(self):
        """Test using different field types in specs."""
        string_field = IndexFieldSpec(name="name", field_type=FieldType.STRING)
        int_field = IndexFieldSpec(name="year", field_type=FieldType.INT32)
        bool_field = IndexFieldSpec(name="active", field_type=FieldType.BOOLEAN)
        dt_field = IndexFieldSpec(name="created_at", field_type=FieldType.DATETIME)

        assert string_field.field_type == FieldType.STRING
        assert int_field.field_type == FieldType.INT32
        assert bool_field.field_type == FieldType.BOOLEAN
        assert dt_field.field_type == FieldType.DATETIME


class TestFieldCategory:
    """Tests for FieldCategory enum."""

    def test_category_values(self):
        """Test that all expected categories exist."""
        assert FieldCategory.COMMON.value == "common"
        assert FieldCategory.CHUNK.value == "chunk"
        assert FieldCategory.DOCUMENT_TYPE.value == "doc_type"

    def test_category_in_field_spec(self):
        """Test using different categories in field specs."""
        common_field = IndexFieldSpec(
            name="country",
            field_type=FieldType.STRING,
            category=FieldCategory.COMMON,
        )
        chunk_field = IndexFieldSpec(
            name="page_number",
            field_type=FieldType.INT32,
            category=FieldCategory.CHUNK,
        )
        doc_type_field = IndexFieldSpec(
            name="operation_number",
            field_type=FieldType.STRING,
            category=FieldCategory.DOCUMENT_TYPE,
        )

        assert common_field.category == FieldCategory.COMMON
        assert chunk_field.category == FieldCategory.CHUNK
        assert doc_type_field.category == FieldCategory.DOCUMENT_TYPE
