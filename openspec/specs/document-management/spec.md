# document-management Specification

## Purpose

Let API consumers read, list, amend, and remove documents already in the system. Covers
single-document retrieval, filtered and paginated listing, PATCH metadata updates with
index synchronisation, and cascading deletion across blob storage, the vector index, and
SQL metadata.

## Requirements

### Requirement: Retrieve A Single Document

The system SHALL return a document's identity fields and stored metadata by `file_id`,
scoped to the effective tenant.

#### Scenario: Document exists

- **WHEN** `GET /api/v1/documents/{id}` is called with `documents.read` and the document exists for the tenant
- **THEN** the response is `200` carrying `file_id`, `filename`, `size_bytes`, `mime_type`, `created_at`, `updated_at`, and the metadata object

#### Scenario: Document absent

- **WHEN** the `file_id` does not exist for the tenant
- **THEN** the response is `404` with error `DocumentNotFound`

### Requirement: List Documents With Filtering, Sorting, And Pagination

The system SHALL list a tenant's documents with optional filters, a sort field and
order, and opaque cursor-based pagination.

#### Scenario: Default listing

- **WHEN** `GET /api/v1/documents` is called with no parameters
- **THEN** up to 20 documents are returned, sorted by upload timestamp descending, together with a pagination object

#### Scenario: Page size bounds

- **WHEN** `limit` is supplied
- **THEN** it must be between 1 and 100 inclusive, and a value outside that range is rejected as a validation error

#### Scenario: Promoted-field filters are applied server-side

- **WHEN** filters such as `document_category`, `document_type`, `operation_number`, `country`, `sector`, `disclosed`, `year`, `operation_type`, `dept_id`, `document_author`, `file_extension`, or `ezshare_id` are supplied
- **THEN** they are pushed into the metadata store query rather than applied after loading

#### Scenario: Tag, source, and department filters

- **WHEN** `tags`, `source`, or `department` are supplied
- **THEN** they are applied in memory over the server-filtered result set, with `tags` matching when any supplied tag is present on the document

#### Scenario: Sorting

- **WHEN** `sort_by` is one of `created_at`, `updated_at`, `filename`, `operation_number`, `year`, `country`, or `sector`
- **THEN** results are ordered by that field in the requested `sort_order`, with an unrecognised field falling back to upload timestamp

#### Scenario: Cursor pagination

- **WHEN** the result set is larger than `limit`
- **THEN** the response carries `total_count`, `has_next`, `has_previous`, and opaque base64 `next_cursor`/`previous_cursor` values that resume the listing at the right offset

#### Scenario: Unreadable cursor

- **WHEN** a supplied cursor cannot be decoded
- **THEN** listing restarts from the first page rather than failing

### Requirement: Update Document Metadata

The system SHALL apply partial (PATCH) metadata updates to a document, increment its
version, and propagate the changed fields to the vector index on a best-effort basis.

#### Scenario: Partial update

- **WHEN** `PATCH /api/v1/documents/{id}` is called with `documents.write` and a subset of metadata fields
- **THEN** only those fields are changed, `last_updated` is refreshed, `file_version` is incremented, and the response is `200` carrying the full updated metadata

#### Scenario: Fields outside the category schema

- **WHEN** the update names a field that is not a promoted field for the document's `document_category`
- **THEN** that field is ignored

#### Scenario: Index synchronisation target

- **WHEN** updated fields are synced to the vector index
- **THEN** the document's own `collection_name` is used as the index, falling back to the configured default index only when the document has none

#### Scenario: Index synchronisation failure

- **WHEN** the vector index update fails
- **THEN** the error is logged and the SQL update still succeeds, returning `200`

#### Scenario: Unknown document

- **WHEN** the `file_id` does not exist for the tenant
- **THEN** the response is `404` with error `DocumentNotFound`

### Requirement: Delete A Document

The system SHALL delete a document's artifacts from every blob container, remove its
chunks from the vector index, and delete its SQL metadata, treating the SQL deletion as
the authoritative step.

#### Scenario: Successful deletion

- **WHEN** `DELETE /api/v1/documents/{id}` is called with `admin` and the document exists
- **THEN** blobs under `{tenant_id}/{file_id}/` are removed from the raw, text, chunks, and embeddings containers, the document's chunks are deleted from its collection index, the SQL records are deleted, and the response is `200` confirming the deletion

#### Scenario: Cascading SQL cleanup

- **WHEN** the metadata record is deleted
- **THEN** the pipeline state, file metadata, chunk index, and processing event rows for that document are removed with it

#### Scenario: Blob cleanup failure does not block

- **WHEN** deleting blobs from one or more containers fails
- **THEN** the failure is logged and SQL cleanup still proceeds

#### Scenario: Missing vector index

- **WHEN** the document's target index does not exist
- **THEN** the vector cleanup is skipped with a warning and SQL cleanup still proceeds

#### Scenario: No index configured

- **WHEN** the document has no `collection_name` and no default index is configured
- **THEN** vector cleanup is skipped and the deletion is still reported as successful

#### Scenario: SQL deletion failure

- **WHEN** the metadata deletion itself fails
- **THEN** the response is `500` with error `StorageError`

#### Scenario: Unknown document

- **WHEN** the `file_id` does not exist for the tenant
- **THEN** the response is `404` with error `DocumentNotFound`
