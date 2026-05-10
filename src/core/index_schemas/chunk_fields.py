"""Chunk-level index fields.

These fields describe the chunk itself (not the parent document) and are
present for every chunk regardless of document type. They enable filtering
by page number, section, or other chunk-specific attributes.
"""

from src.core.index_schemas.field_spec import FieldCategory, FieldType, IndexFieldSpec

CHUNK_INDEX_FIELDS: tuple[IndexFieldSpec, ...] = (
    IndexFieldSpec(
        name="page_number",
        field_type=FieldType.INT32,
        filterable=True,
        sortable=True,
        category=FieldCategory.CHUNK,
        description="Page number in source document (1-indexed)",
    ),
    IndexFieldSpec(
        name="section_path",
        field_type=FieldType.STRING,
        filterable=True,
        category=FieldCategory.CHUNK,
        description="Hierarchical section path (e.g., 'Chapter 1 > Section 1.2')",
    ),
    IndexFieldSpec(
        name="has_table",
        field_type=FieldType.BOOLEAN,
        filterable=True,
        category=FieldCategory.CHUNK,
        description="Whether chunk contains tabular data",
    ),
    IndexFieldSpec(
        name="table_id",
        field_type=FieldType.STRING,
        filterable=True,
        category=FieldCategory.CHUNK,
        description="Identifier for table if has_table is true",
    ),
    # Processing metadata (useful for debugging/analytics)
    IndexFieldSpec(
        name="chunking_strategy",
        field_type=FieldType.STRING,
        filterable=True,
        category=FieldCategory.CHUNK,
        description="Strategy used to chunk this document",
    ),
    IndexFieldSpec(
        name="token_count",
        field_type=FieldType.INT32,
        filterable=True,
        category=FieldCategory.CHUNK,
        description="Number of tokens in this chunk",
    ),
    IndexFieldSpec(
        name="chunk_size",
        field_type=FieldType.INT32,
        filterable=False,
        category=FieldCategory.CHUNK,
        description="Size of chunk in characters",
    ),
    IndexFieldSpec(
        name="overlap_chars",
        field_type=FieldType.INT32,
        filterable=False,
        category=FieldCategory.CHUNK,
        description="Number of overlap characters with adjacent chunks",
    ),
    IndexFieldSpec(
        name="model_version",
        field_type=FieldType.STRING,
        filterable=True,
        category=FieldCategory.CHUNK,
        description="Embedding model version used",
    ),
)
