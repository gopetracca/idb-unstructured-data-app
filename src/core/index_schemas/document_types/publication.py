"""Index fields specific to Research Publications.

Research publications include journal articles, working papers, book chapters,
conference papers, and other academic/research materials. These fields enable
filtering by publication-specific attributes during semantic search.

NOTE: This is prepared for future implementation. The fields defined here
represent common publication metadata that would be useful for filtering.
"""

from src.core.index_schemas.field_spec import FieldCategory, FieldType, IndexFieldSpec

PUBLICATION_INDEX_FIELDS: tuple[IndexFieldSpec, ...] = (
    IndexFieldSpec(
        name="journal",
        field_type=FieldType.STRING,
        filterable=True,
        sortable=True,
        category=FieldCategory.DOCUMENT_TYPE,
        description="Journal or publication venue name",
    ),
    IndexFieldSpec(
        name="doi",
        field_type=FieldType.STRING,
        filterable=True,
        category=FieldCategory.DOCUMENT_TYPE,
        description="Digital Object Identifier",
    ),
    IndexFieldSpec(
        name="issn",
        field_type=FieldType.STRING,
        filterable=True,
        category=FieldCategory.DOCUMENT_TYPE,
        description="International Standard Serial Number",
    ),
    IndexFieldSpec(
        name="peer_reviewed",
        field_type=FieldType.BOOLEAN,
        filterable=True,
        category=FieldCategory.DOCUMENT_TYPE,
        description="Whether the publication was peer-reviewed",
    ),
    IndexFieldSpec(
        name="publication_type",
        field_type=FieldType.STRING,
        filterable=True,
        category=FieldCategory.DOCUMENT_TYPE,
        description="Type of publication (journal_article, working_paper, book_chapter)",
    ),
    IndexFieldSpec(
        name="publication_date",
        field_type=FieldType.DATETIME,
        filterable=True,
        sortable=True,
        category=FieldCategory.DOCUMENT_TYPE,
        description="Date of publication",
    ),
)
