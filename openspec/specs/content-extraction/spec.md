# content-extraction Specification

## Purpose

Turn an uploaded source document into machine-readable text. Azure Document
Intelligence analyses the raw blob and produces markdown plus extraction metadata, which
is stored in the text container and recorded on the document as the single source of
truth for where its extracted text lives. This is the `convert` stage of the pipeline.

## Requirements

### Requirement: Extract Content From A Stored Document

The system SHALL extract text from a document already present in the raw container and
store the result as JSON in the text container.

#### Scenario: Successful extraction

- **WHEN** `POST /api/v1/contents` is called with `documents.write` and a `file_id` whose raw blob exists and whose content type is supported
- **THEN** the document is analysed, the markdown output plus extraction metadata is written to `{tenant_id}/{file_id}/text.json` in the output container, and the response is `202` carrying `file_id`, `status`, `markdown_url`, `correlation_id`, and `processing_time_ms`

#### Scenario: Blob reference is the source of truth

- **WHEN** the source blob is located
- **THEN** the path recorded in the document's `raw_blob_ref` column is used, not a path reconstructed from convention

#### Scenario: Missing raw blob reference

- **WHEN** the document record has no `raw_blob_ref`
- **THEN** a document processing error for stage `convert` is raised with reason `missing_raw_blob_ref`

#### Scenario: Blob absent from storage

- **WHEN** the recorded `raw_blob_ref` does not exist in the source container
- **THEN** the response is `404` with error `DocumentNotFound`

#### Scenario: Unknown document

- **WHEN** the `file_id` has no record for the tenant
- **THEN** the response is `404` with error `DocumentNotFound`

#### Scenario: Unsupported format

- **WHEN** the document's content type is not supported by the extraction adapter
- **THEN** the response is `400` and the error names the content type and the supported formats

#### Scenario: Extraction failure

- **WHEN** the extraction adapter raises
- **THEN** the pipeline state is marked failed with the error message and the response is `500`

### Requirement: Text Blob Reference Recorded

The system SHALL record the extracted-text blob path on the document record so
downstream stages locate the text without reconstructing paths.

#### Scenario: Reference written after extraction

- **WHEN** the text JSON is stored
- **THEN** the document's `text_blob_ref` is updated to that blob path before the stage reports success

### Requirement: Supported Extraction Formats

The system SHALL expose the set of content types the extraction adapter accepts, and
SHALL accept PDF, DOCX, PNG, JPEG, TIFF, BMP, and plain text by default.

#### Scenario: Querying supported formats

- **WHEN** `GET /documents/supported-formats` is called with `documents.read`
- **THEN** the response lists the content types the configured adapter supports

#### Scenario: Fake adapter for local development

- **WHEN** `DOCUMENT_INTELLIGENCE_USE_FAKE` is true
- **THEN** a fake adapter produces deterministic output after a simulated delay instead of calling Azure

### Requirement: Stage Event Logging For Extraction

The system SHALL record a `convert` processing event with status and duration for every
extraction attempt, and SHALL NOT let event-logging failures affect the extraction
outcome.

#### Scenario: Successful extraction is recorded

- **WHEN** extraction completes
- **THEN** a `convert` event with status `success` and the elapsed duration is logged

#### Scenario: Failed extraction is recorded

- **WHEN** extraction fails for any reason
- **THEN** a `convert` event with status `failed` and the error message is logged

#### Scenario: Event store unavailable

- **WHEN** writing the processing event raises
- **THEN** the failure is logged as a warning and the extraction result is unchanged

### Requirement: Deprecated Analyze Endpoint

The system SHALL retain `POST /documents/analyze` as an alias for content extraction for
existing consumers.

#### Scenario: Analyze request

- **WHEN** `POST /documents/analyze` is called with `documents.write`
- **THEN** the same extraction behaviour applies and the response is `202`

### Requirement: Unimplemented Content Read Endpoints

The system SHALL reserve the content read and delete routes and SHALL report them as not
implemented until they are built.

#### Scenario: Listing, reading, or deleting content

- **WHEN** `GET /api/v1/contents`, `GET /api/v1/contents/{id}`, `GET /api/v1/contents/{id}/text`, or `DELETE /api/v1/contents/{id}` is called
- **THEN** the response is `501 Not Implemented`
