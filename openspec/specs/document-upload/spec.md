# document-upload Specification

## Purpose

Accept a source document (PDF or Word) together with its business metadata, persist the
bytes to blob storage and the metadata to SQL, and enqueue the document for asynchronous
RAG processing. Uploads are the single entry point into the pipeline and the point at
which duplicate detection, type/size validation, and document-category typing happen.

## Requirements

### Requirement: Typed Upload Endpoints

The system SHALL expose a dedicated upload endpoint per document category with typed
form fields, and SHALL retain a generic endpoint that selects the schema by a
`document_type` form field.

#### Scenario: Operational upload

- **WHEN** a client POSTs a file to `/api/v1/documents/operational` with the operational form fields
- **THEN** the document is stored with `document_category` `operational` and the operational-specific fields `operation_number`, `sector`, `operation_type`, and `dept_id`
- **AND** the response is `201` carrying `file_id`, `filename`, `size_bytes`, `mime_type`, `uploaded_at`, and the stored metadata

#### Scenario: Publication upload

- **WHEN** a client POSTs a file to `/api/v1/documents/publication` with the publication form fields
- **THEN** the document is stored with `document_category` `publication` and the publication-specific fields `journal`, `doi`, `issn`, `peer_reviewed`, `publication_type`, and `publication_date`

#### Scenario: Generic upload endpoint

- **WHEN** a client POSTs to `/api/v1/documents` with a `document_type` form field and a `metadata` JSON string
- **THEN** the metadata is validated against that category's schema and the value of `document_type` is stored as the `document_category` discriminator
- **AND** the endpoint is marked deprecated in the OpenAPI document in favour of the typed endpoints

#### Scenario: Unknown document type on the generic endpoint

- **WHEN** `document_type` is not a registered category
- **THEN** the response is `400` with error `InvalidDocumentType` listing the available categories

#### Scenario: Malformed metadata JSON

- **WHEN** the `metadata` form field is not valid JSON
- **THEN** the response is `400` with error `InvalidMetadataJSON`

#### Scenario: Metadata failing the category schema

- **WHEN** the parsed metadata violates the category's Pydantic schema
- **THEN** the response is `400` with error `InvalidMetadata` and `details` carrying the field-level errors

#### Scenario: Upload requires write permission

- **WHEN** a caller without `documents.write` invokes any upload endpoint
- **THEN** the response is `403 Forbidden`

### Requirement: Upload Validation

The system SHALL validate the file's MIME type and size before performing any I/O, and
SHALL reject anything outside the configured allow-list and size limit.

#### Scenario: Disallowed MIME type

- **WHEN** the uploaded file's content type is not in `FILE_UPLOAD_ALLOWED_MIME_TYPES` (by default PDF and DOCX)
- **THEN** the response is `400` with error `InvalidFileType` and no blob is written

#### Scenario: Oversized file

- **WHEN** the uploaded file exceeds `FILE_UPLOAD_MAX_FILE_SIZE_MB` (default 50 MB)
- **THEN** the response is `413` with error `FileSizeExceeded` and no blob is written

#### Scenario: Bounded read

- **WHEN** the request body is read
- **THEN** it is read in bounded chunks that stop at the configured limit rather than buffering an unbounded body

### Requirement: Duplicate Detection By External Identifier

The system SHALL require a unique `ezshare_id` per tenant and SHALL reject an upload
whose `ezshare_id` already exists, before writing any bytes.

#### Scenario: Duplicate ezshare_id

- **WHEN** an upload carries an `ezshare_id` already recorded for the tenant
- **THEN** the response is `409` with error `DuplicateDocument`, naming the existing `file_id`
- **AND** no blob is written and no metadata row is created

#### Scenario: First upload of an identifier

- **WHEN** the `ezshare_id` is unused for the tenant
- **THEN** the upload proceeds

### Requirement: Document Persistence On Upload

The system SHALL assign a server-generated `file_id`, store the raw bytes under a
tenant-scoped blob path, compute a content hash, and persist an identity record,
a pipeline-state record, and a category-typed metadata record as one unit.

#### Scenario: Successful persistence

- **WHEN** validation and duplicate checks pass
- **THEN** a UUID `file_id` is generated, the bytes are written to `{tenant_id}/{file_id}/{filename}` in the raw container, a SHA-256 content hash is computed, and the document, pipeline state, and metadata records are created together

#### Scenario: Initial pipeline state

- **WHEN** the document records are created
- **THEN** the pipeline state starts at stage `dispatcher` with overall status `queued` and records the requested chunking strategy

#### Scenario: Metadata rollback on persistence failure

- **WHEN** the blob upload succeeds but the metadata write fails
- **THEN** the uploaded blob is deleted on a best-effort basis and the response is `500` with error `StorageError`

#### Scenario: File extension derived from filename

- **WHEN** the metadata omits `file_extension`
- **THEN** it is derived from the uploaded filename's extension

#### Scenario: Only promoted fields are persisted

- **WHEN** metadata contains keys outside the category's promoted field set
- **THEN** those keys are discarded and only promoted fields are written to SQL columns

### Requirement: Enqueue For Asynchronous Processing

The system SHALL publish the uploaded document to the raw-file processing queue after
persistence, and SHALL NOT fail the upload when publishing fails.

#### Scenario: Successful enqueue

- **WHEN** persistence completes
- **THEN** a message carrying the tenant, file id, file version, filename, and chunking strategy is published to the configured processing queue

#### Scenario: Enqueue failure

- **WHEN** the queue publish raises
- **THEN** the error is logged and the upload still returns `201`, leaving the document persisted but unprocessed

### Requirement: Per-Upload Chunking Strategy

The system SHALL let each upload declare the chunking strategy to be applied later in
the pipeline, defaulting to fixed-size chunking when unspecified.

#### Scenario: Strategy supplied

- **WHEN** the upload form carries `chunking_strategy_name` and `chunking_parameters`
- **THEN** the parsed strategy is persisted on the pipeline state and carried in the queue payload

#### Scenario: Strategy omitted

- **WHEN** no chunking strategy is supplied
- **THEN** fixed-size chunking with the default chunk size and overlap is used
