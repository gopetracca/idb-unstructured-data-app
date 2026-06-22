"""Unit tests for Index Schema Registry."""

import pytest

from src.core.index_schemas import (
    CHUNK_INDEX_FIELDS,
    COMMON_INDEX_FIELDS,
    OPERATIONAL_INDEX_FIELDS,
    PUBLICATION_INDEX_FIELDS,
    FieldCategory,
    FieldType,
    IndexFieldSpec,
    get_base_schema,
    get_field_by_name,
    get_filterable_fields,
    get_index_schema,
    get_sortable_fields,
    get_type_specific_schema,
    list_document_types,
)


class TestListDocumentTypes:
    """Tests for list_document_types function."""

    def test_returns_sorted_list(self):
        """Test that document types are returned sorted."""
        types = list_document_types()
        assert types == sorted(types)

    def test_includes_operational(self):
        """Test that operational document type is registered."""
        types = list_document_types()
        assert "operational" in types

    def test_includes_publication(self):
        """Test that publication document type is registered."""
        types = list_document_types()
        assert "publication" in types


class TestGetIndexSchema:
    """Tests for get_index_schema function."""

    def test_operational_schema_includes_base_fields(self):
        """Test that operational schema includes common and chunk fields."""
        schema = get_index_schema("operational")
        field_names = {f.name for f in schema}

        # Check common fields
        assert "country" in field_names
        assert "year" in field_names
        assert "document_type" in field_names
        assert "language" in field_names

        # Check chunk fields
        assert "page_number" in field_names
        assert "section_path" in field_names
        assert "has_table" in field_names

    def test_operational_schema_includes_type_specific_fields(self):
        """Test that operational schema includes operational-specific fields."""
        schema = get_index_schema("operational")
        field_names = {f.name for f in schema}

        assert "operation_number" in field_names
        assert "sector" in field_names
        assert "operation_type" in field_names
        assert "dept_id" in field_names

    def test_publication_schema_includes_base_fields(self):
        """Test that publication schema includes common and chunk fields."""
        schema = get_index_schema("publication")
        field_names = {f.name for f in schema}

        # Check common fields
        assert "country" in field_names
        assert "year" in field_names
        assert "document_type" in field_names

        # Check chunk fields
        assert "page_number" in field_names
        assert "section_path" in field_names

    def test_publication_schema_includes_type_specific_fields(self):
        """Test that publication schema includes publication-specific fields."""
        schema = get_index_schema("publication")
        field_names = {f.name for f in schema}

        assert "journal" in field_names
        assert "doi" in field_names
        assert "peer_reviewed" in field_names
        assert "publication_type" in field_names

    def test_publication_schema_excludes_operational_fields(self):
        """Test that publication schema does NOT include operational fields."""
        schema = get_index_schema("publication")
        field_names = {f.name for f in schema}

        assert "operation_number" not in field_names
        assert "sector" not in field_names
        assert "dept_id" not in field_names

    def test_operational_schema_excludes_publication_fields(self):
        """Test that operational schema does NOT include publication fields."""
        schema = get_index_schema("operational")
        field_names = {f.name for f in schema}

        assert "journal" not in field_names
        assert "doi" not in field_names
        assert "issn" not in field_names

    def test_unknown_type_raises_error(self):
        """Test that unknown document category raises ValueError."""
        with pytest.raises(ValueError, match="Unknown document category: 'unknown'"):
            get_index_schema("unknown")

    def test_error_message_includes_available_types(self):
        """Test that error message lists available types."""
        with pytest.raises(ValueError) as exc_info:
            get_index_schema("invalid_type")

        assert "operational" in str(exc_info.value)
        assert "publication" in str(exc_info.value)

    def test_schema_returns_tuple(self):
        """Test that schema is returned as immutable tuple."""
        schema = get_index_schema("operational")
        assert isinstance(schema, tuple)

    def test_all_fields_are_index_field_spec(self):
        """Test that all fields in schema are IndexFieldSpec instances."""
        schema = get_index_schema("operational")
        for field in schema:
            assert isinstance(field, IndexFieldSpec)


class TestGetBaseSchema:
    """Tests for get_base_schema function."""

    def test_includes_common_fields(self):
        """Test that base schema includes common fields."""
        schema = get_base_schema()
        field_names = {f.name for f in schema}

        assert "country" in field_names
        assert "year" in field_names
        assert "document_type" in field_names
        assert "tags" in field_names

    def test_includes_chunk_fields(self):
        """Test that base schema includes chunk fields."""
        schema = get_base_schema()
        field_names = {f.name for f in schema}

        assert "page_number" in field_names
        assert "section_path" in field_names
        assert "has_table" in field_names
        assert "token_count" in field_names

    def test_excludes_type_specific_fields(self):
        """Test that base schema excludes document-type-specific fields."""
        schema = get_base_schema()
        field_names = {f.name for f in schema}

        # No operational fields
        assert "operation_number" not in field_names
        assert "sector" not in field_names

        # No publication fields
        assert "journal" not in field_names
        assert "doi" not in field_names

    def test_equals_common_plus_chunk(self):
        """Test that base schema equals common + chunk fields."""
        base = get_base_schema()
        expected = COMMON_INDEX_FIELDS + CHUNK_INDEX_FIELDS
        assert base == expected


class TestGetTypeSpecificSchema:
    """Tests for get_type_specific_schema function."""

    def test_operational_returns_only_operational_fields(self):
        """Test that operational type-specific schema returns only operational fields."""
        schema = get_type_specific_schema("operational")
        assert schema == OPERATIONAL_INDEX_FIELDS

    def test_publication_returns_only_publication_fields(self):
        """Test that publication type-specific schema returns only publication fields."""
        schema = get_type_specific_schema("publication")
        assert schema == PUBLICATION_INDEX_FIELDS

    def test_unknown_type_raises_error(self):
        """Test that unknown document category raises ValueError."""
        with pytest.raises(ValueError, match="Unknown document category"):
            get_type_specific_schema("unknown")


class TestGetFieldByName:
    """Tests for get_field_by_name function."""

    def test_find_common_field(self):
        """Test finding a common field by name."""
        field = get_field_by_name("operational", "country")

        assert field is not None
        assert field.name == "country"
        assert field.category == FieldCategory.COMMON

    def test_find_chunk_field(self):
        """Test finding a chunk field by name."""
        field = get_field_by_name("operational", "page_number")

        assert field is not None
        assert field.name == "page_number"
        assert field.category == FieldCategory.CHUNK

    def test_find_type_specific_field(self):
        """Test finding a type-specific field by name."""
        field = get_field_by_name("operational", "operation_number")

        assert field is not None
        assert field.name == "operation_number"
        assert field.category == FieldCategory.DOCUMENT_TYPE

    def test_field_not_in_type_returns_none(self):
        """Test that searching for field not in type returns None."""
        # journal is a publication field, not operational
        field = get_field_by_name("operational", "journal")
        assert field is None

    def test_nonexistent_field_returns_none(self):
        """Test that nonexistent field returns None."""
        field = get_field_by_name("operational", "nonexistent_field")
        assert field is None


class TestGetFilterableFields:
    """Tests for get_filterable_fields function."""

    def test_returns_only_filterable_fields(self):
        """Test that only filterable fields are returned."""
        fields = get_filterable_fields("operational")

        for field in fields:
            assert field.filterable is True

    def test_includes_filterable_common_fields(self):
        """Test that filterable common fields are included."""
        fields = get_filterable_fields("operational")
        field_names = {f.name for f in fields}

        assert "country" in field_names
        assert "year" in field_names
        assert "document_type" in field_names

    def test_excludes_non_filterable_fields(self):
        """Test that non-filterable fields are excluded."""
        fields = get_filterable_fields("operational")
        field_names = {f.name for f in fields}

        # blob_name is not filterable
        assert "blob_name" not in field_names


class TestGetSortableFields:
    """Tests for get_sortable_fields function."""

    def test_returns_only_sortable_fields(self):
        """Test that only sortable fields are returned."""
        fields = get_sortable_fields("operational")

        for field in fields:
            assert field.sortable is True

    def test_includes_sortable_fields(self):
        """Test that known sortable fields are included."""
        fields = get_sortable_fields("operational")
        field_names = {f.name for f in fields}

        assert "year" in field_names
        assert "country" in field_names
        assert "page_number" in field_names

    def test_excludes_non_sortable_fields(self):
        """Test that non-sortable fields are excluded."""
        fields = get_sortable_fields("operational")
        field_names = {f.name for f in fields}

        # tags is a collection, cannot be sortable
        assert "tags" not in field_names


class TestFieldDefinitions:
    """Tests for the actual field definitions."""

    def test_common_fields_have_correct_categories(self):
        """Test that common fields have COMMON category."""
        for field in COMMON_INDEX_FIELDS:
            assert field.category == FieldCategory.COMMON

    def test_chunk_fields_have_correct_categories(self):
        """Test that chunk fields have CHUNK category."""
        for field in CHUNK_INDEX_FIELDS:
            assert field.category == FieldCategory.CHUNK

    def test_operational_fields_have_correct_categories(self):
        """Test that operational fields have DOCUMENT_TYPE category."""
        for field in OPERATIONAL_INDEX_FIELDS:
            assert field.category == FieldCategory.DOCUMENT_TYPE

    def test_publication_fields_have_correct_categories(self):
        """Test that publication fields have DOCUMENT_TYPE category."""
        for field in PUBLICATION_INDEX_FIELDS:
            assert field.category == FieldCategory.DOCUMENT_TYPE

    def test_tags_field_is_collection(self):
        """Test that tags field is marked as collection."""
        field = get_field_by_name("operational", "tags")
        assert field is not None
        assert field.is_collection is True

    def test_year_field_is_int32(self):
        """Test that year field has correct type."""
        field = get_field_by_name("operational", "year")
        assert field is not None
        assert field.field_type == FieldType.INT32

    def test_disclosed_field_is_boolean(self):
        """Test that disclosed field is boolean type."""
        field = get_field_by_name("operational", "disclosed")
        assert field is not None
        assert field.field_type == FieldType.BOOLEAN

    def test_peer_reviewed_field_is_boolean(self):
        """Test that peer_reviewed field is boolean type."""
        field = get_field_by_name("publication", "peer_reviewed")
        assert field is not None
        assert field.field_type == FieldType.BOOLEAN
