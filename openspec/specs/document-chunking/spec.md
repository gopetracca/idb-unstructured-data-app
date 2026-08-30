# document-chunking Specification

## Purpose

Split a document's extracted text into retrievable chunks according to a declared
strategy, store each chunk as a blob, and record a queryable chunk index in SQL with the
positional and structural metadata search needs (page number, section path, character
offsets). This is the `chunk` stage of the pipeline.

## Requirements

### Requirement: Chunk A Document

The system SHALL chunk a document's extracted text using the requested strategy, store
each chunk in the chunks container, and record a chunk index row per chunk.

#### Scenario: Successful chunking

- **WHEN** `POST /api/v1/chunks` is called with `documents.write` for a document whose extracted text exists
- **THEN** the text is chunked, each chunk is written to `{tenant_id}/{file_id}/chunks/{chunk_id}.json`, a chunk index row is created per chunk, and the response is `202` carrying `file_id`, `status`, `chunk_count`, `chunks_url`, the strategy used, `correlation_id`, and `processing_time_ms`

#### Scenario: Text located via the recorded reference

- **WHEN** the source text is loaded
- **THEN** the document's `text_blob_ref` column is used as the source of truth for its location

#### Scenario: Missing text reference

- **WHEN** the document has no `text_blob_ref`
- **THEN** a chunking error with reason `missing_text_blob_ref` is raised

#### Scenario: Text blob absent

- **WHEN** the recorded text blob does not exist in the source container
- **THEN** a text-not-found error is raised and the response is `404`

#### Scenario: Empty extracted text

- **WHEN** the text JSON contains no `extracted_text` content
- **THEN** a chunking error is raised rather than producing zero chunks silently

#### Scenario: Unknown document

- **WHEN** the `file_id` has no record for the tenant
- **THEN** the response is `404` with error `DocumentNotFound`

#### Scenario: Chunk count recorded

- **WHEN** chunking completes
- **THEN** the document's pipeline state is updated with the resulting chunk count

### Requirement: Idempotent Rechunking

The system SHALL delete a document's existing chunk index rows before writing new ones,
so rechunking a document does not accumulate stale chunks.

#### Scenario: Chunking a document a second time

- **WHEN** a document that already has chunks is chunked again
- **THEN** the previous chunk index rows are removed first and only the new chunks remain indexed

### Requirement: Chunking Strategies

The system SHALL support a declared set of chunking strategies, each with its own typed
parameter model, and SHALL reject a strategy the configured adapter does not support.

#### Scenario: Available strategies

- **WHEN** the Chonkie adapter is configured (the default)
- **THEN** `fixed_size`, `markdown_aware`, and `recursive_chunking` are supported, and `semantic_chunking` is supported only when `CHUNKING_ENABLE_SEMANTIC_CHUNKING` is true

#### Scenario: Unsupported strategy requested

- **WHEN** a request names a strategy the adapter does not support
- **THEN** an invalid-strategy error listing the supported strategies is raised and the response is `400`

#### Scenario: Strategy parameters are typed per strategy

- **WHEN** a strategy is supplied with parameters
- **THEN** the parameters are validated against that strategy's model, unknown keys are rejected, and a parameter set that does not match the strategy is an error

#### Scenario: Chunk size and overlap bounds

- **WHEN** `chunk_size` or `chunk_overlap` is supplied
- **THEN** `chunk_size` must be between 50 and 4096, `chunk_overlap` between 0 and 500, and `chunk_overlap` must be strictly less than `chunk_size`

#### Scenario: Strategy defaults

- **WHEN** a strategy is named without parameters
- **THEN** the strategy's defaults apply: 512 characters for `fixed_size` and `recursive_chunking`, 1024 for `semantic_chunking` and `markdown_aware`, with an overlap of 50

### Requirement: Structure-Aware Chunk Metadata

The system SHALL preserve document structure when chunking, keeping HTML tables intact
and recording the section path and page number each chunk came from.

#### Scenario: Tables kept atomic

- **WHEN** the extracted text contains HTML tables
- **THEN** each outermost table is extracted before chunking and emitted as its own atomic chunk rather than being split

#### Scenario: Section path tracking

- **WHEN** the text contains markdown headings
- **THEN** each chunk records the heading path it falls under

#### Scenario: Page number tracking

- **WHEN** the text contains Document Intelligence page markers
- **THEN** each chunk records the page it originated from

#### Scenario: Token counting

- **WHEN** a token-based strategy runs
- **THEN** tokens are counted with the `cl100k_base` encoding, loaded once at construction so no network call happens at runtime

#### Scenario: Offline tokenizer availability

- **WHEN** the tokenizer encoding cannot be loaded at construction
- **THEN** the adapter fails fast with an error naming the offline cache requirement

### Requirement: List A Document's Chunks

The system SHALL return a document's chunks with their positional metadata, paginated.

#### Scenario: Listing chunks

- **WHEN** `GET /api/v1/chunks` is called with `documents.read` and either `content_id` or `document_id`
- **THEN** the response is `200` carrying each chunk's `chunk_id`, `chunk_index`, `text_preview`, `char_count`, `start_char`, `end_char`, and `page_number`, plus pagination

#### Scenario: No identifier supplied

- **WHEN** neither `content_id` nor `document_id` is supplied
- **THEN** the response is `400`

#### Scenario: Pagination bounds

- **WHEN** `page_number` and `page_size` are supplied
- **THEN** `page_number` must be at least 1 and `page_size` between 1 and 100, defaulting to page 1 with 20 items

### Requirement: Stage Event Logging For Chunking

The system SHALL record a `chunk` processing event with status and duration for every
chunking attempt.

#### Scenario: Successful chunking is recorded

- **WHEN** chunking completes
- **THEN** a `chunk` event with status `success` and the elapsed duration is logged

#### Scenario: Failed chunking is recorded

- **WHEN** chunking fails
- **THEN** a `chunk` event with status `failed` and the error message is logged, and unexpected failures also mark the pipeline state failed

### Requirement: Unimplemented Chunk Read Endpoints

The system SHALL reserve the single-chunk read and delete routes and SHALL report them
as not implemented until they are built.

#### Scenario: Reading or deleting a single chunk

- **WHEN** `GET /api/v1/chunks/{id}` or `DELETE /api/v1/chunks/{id}` is called
- **THEN** the response is `501 Not Implemented`

### Requirement: Chunk Record Invariants

The system SHALL enforce the shape of a chunk and the metadata it carries, so downstream
stages and search results can rely on them.

#### Scenario: Position

- **WHEN** a chunk is produced
- **THEN** its index within the file is zero-based and non-negative, and its start and end character offsets are non-negative

#### Scenario: Preview

- **WHEN** a chunk preview is stored or returned
- **THEN** it is the first 100 characters of the chunk text, and empty when the text is empty

#### Scenario: Chunk metadata carried

- **WHEN** a chunk is produced
- **THEN** its metadata records the overlap, token count, section path, page label, whether it is a table and that table's identifier, and the strategy and chunk size that produced it
