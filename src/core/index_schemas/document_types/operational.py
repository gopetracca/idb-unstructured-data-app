"""Index fields specific to Operational Documents.

Operational documents include loans, grants, technical cooperation documents,
and other IDB operational materials. These fields enable filtering by
operation-specific attributes during semantic search.
"""

from src.core.index_schemas.field_spec import FieldCategory, FieldType, IndexFieldSpec

OPERATIONAL_INDEX_FIELDS: tuple[IndexFieldSpec, ...] = (
    IndexFieldSpec(
        name="operation_number",
        field_type=FieldType.STRING,
        filterable=True,
        sortable=True,
        category=FieldCategory.DOCUMENT_TYPE,
        description="IDB operation identifier (e.g., UR-L1234, BR-T1456)",
    ),
    IndexFieldSpec(
        name="sector",
        field_type=FieldType.STRING,
        filterable=True,
        sortable=True,
        category=FieldCategory.DOCUMENT_TYPE,
        description="Primary sector (e.g., TRANSPORT, HEALTH, EDUCATION)",
    ),
    IndexFieldSpec(
        name="operation_type",
        field_type=FieldType.STRING,
        filterable=True,
        category=FieldCategory.DOCUMENT_TYPE,
        description="Type of operation (e.g., Loan, Grant, TC)",
    ),
    IndexFieldSpec(
        name="dept_id",
        field_type=FieldType.STRING,
        filterable=True,
        category=FieldCategory.DOCUMENT_TYPE,
        description="Department identifier (e.g., INE/TSP, SCL/EDU)",
    ),
    IndexFieldSpec(
        name="access_to_information_policy",
        field_type=FieldType.STRING,
        filterable=True,
        category=FieldCategory.DOCUMENT_TYPE,
        description="Access to information policy classification",
    ),
    IndexFieldSpec(
        name="document_publish_date",
        field_type=FieldType.DATETIME,
        filterable=True,
        sortable=True,
        category=FieldCategory.DOCUMENT_TYPE,
        description="Date the document was published",
    ),
    IndexFieldSpec(
        name="document_approval_date",
        field_type=FieldType.DATETIME,
        filterable=True,
        sortable=True,
        category=FieldCategory.DOCUMENT_TYPE,
        description="Date the document was approved",
    ),
)
