"""Common index fields shared by all document types.

These fields appear in EVERY document type's index schema and represent
metadata that is universally applicable across operational documents,
publications, and any future document types.
"""

from src.core.index_schemas.field_spec import FieldCategory, FieldType, IndexFieldSpec

COMMON_INDEX_FIELDS: tuple[IndexFieldSpec, ...] = (
    # Document identification
    IndexFieldSpec(
        name="document_type",
        field_type=FieldType.STRING,
        filterable=True,
        category=FieldCategory.COMMON,
        description="Discriminator for document type (operational, publication, etc.)",
    ),
    IndexFieldSpec(
        name="collection_name",
        field_type=FieldType.STRING,
        filterable=True,
        category=FieldCategory.COMMON,
        description="Logical collection/index the document belongs to",
    ),
    IndexFieldSpec(
        name="ezshare_id",
        field_type=FieldType.STRING,
        filterable=True,
        category=FieldCategory.COMMON,
        description="External document identifier from source system",
    ),
    # Document attributes commonly filtered
    IndexFieldSpec(
        name="country",
        field_type=FieldType.STRING,
        filterable=True,
        sortable=True,
        category=FieldCategory.COMMON,
        description="Country associated with the document",
    ),
    IndexFieldSpec(
        name="year",
        field_type=FieldType.INT32,
        filterable=True,
        sortable=True,
        category=FieldCategory.COMMON,
        description="Publication or approval year",
    ),
    IndexFieldSpec(
        name="language",
        field_type=FieldType.STRING,
        filterable=True,
        category=FieldCategory.COMMON,
        description="Document language (ISO 639-1 code)",
    ),
    IndexFieldSpec(
        name="disclosed",
        field_type=FieldType.BOOLEAN,
        filterable=True,
        category=FieldCategory.COMMON,
        description="Whether document is publicly disclosed",
    ),
    IndexFieldSpec(
        name="tags",
        field_type=FieldType.STRING,
        filterable=True,
        is_collection=True,
        category=FieldCategory.COMMON,
        description="Document tags for categorization",
    ),
    # Fields needed for response building (not necessarily filtering)
    IndexFieldSpec(
        name="blob_name",
        field_type=FieldType.STRING,
        filterable=False,
        category=FieldCategory.COMMON,
        description="Original filename, stored to avoid SQL round-trip on search",
    ),
    IndexFieldSpec(
        name="document_name",
        field_type=FieldType.STRING,
        filterable=True,
        sortable=True,
        category=FieldCategory.COMMON,
        description="Document title/name",
    ),
    IndexFieldSpec(
        name="document_author",
        field_type=FieldType.STRING,
        filterable=True,
        category=FieldCategory.COMMON,
        description="Document author or authoring team",
    ),
    IndexFieldSpec(
        name="department",
        field_type=FieldType.STRING,
        filterable=True,
        category=FieldCategory.COMMON,
        description="Department that produced the document",
    ),
    IndexFieldSpec(
        name="source",
        field_type=FieldType.STRING,
        filterable=True,
        category=FieldCategory.COMMON,
        description="Source system or origin of the document",
    ),
    IndexFieldSpec(
        name="file_extension",
        field_type=FieldType.STRING,
        filterable=True,
        category=FieldCategory.COMMON,
        description="File extension (e.g., .pdf, .docx)",
    ),
)
