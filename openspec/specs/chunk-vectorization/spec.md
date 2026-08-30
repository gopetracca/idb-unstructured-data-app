# chunk-vectorization Specification

## Purpose

Turn a document's chunks into embedding vectors using Azure OpenAI, store each embedding
alongside its searchable metadata in the embeddings container, and track per-chunk
embedding status so the stage is resumable. This is the `vectorize` stage of the
pipeline.

## Requirements

### Requirement: Vectorize A Document's Chunks

The system SHALL generate embeddings for a document's not-yet-embedded chunks, store
each embedding as a blob, and mark the corresponding chunk index rows as embedded.

#### Scenario: Successful vectorization

- **WHEN** `POST /api/v1/embeddings` is called with `documents.write` for a document that has pending chunks
- **THEN** embeddings are generated, stored under `{tenant_id}/{file_id}/embeddings/`, the chunk index rows are marked embedded, the pipeline state's embedded count is updated, and the response is `202` carrying `total_chunks`, `embedded_chunks`, `failed_chunks`, the model, the vector dimension, and `embeddings_url`

#### Scenario: Unknown document

- **WHEN** the `file_id` has no record for the tenant
- **THEN** the response is `404` with error `DocumentNotFound`

#### Scenario: Document has no chunks

- **WHEN** the document has no chunk index rows at all
- **THEN** a chunks-not-found error is raised and the response is `404`

#### Scenario: Chunks located via recorded references

- **WHEN** chunk content is loaded
- **THEN** each chunk index row's `chunk_blob_ref` is used as the source of truth, and a row missing that reference is skipped with a warning rather than failing the stage

### Requirement: Resumable Vectorization

The system SHALL vectorize only chunks that are not yet embedded, so a re-run after a
partial failure completes the remaining work instead of redoing all of it.

#### Scenario: Partially embedded document

- **WHEN** some of a document's chunks are already embedded
- **THEN** only the pending chunks are sent to the embedding provider

#### Scenario: Fully embedded document

- **WHEN** every chunk is already embedded
- **THEN** the stage returns success immediately with the existing counts and without calling the embedding provider

### Requirement: Batched Embedding Generation

The system SHALL send chunks to the embedding provider in batches of the requested batch
size and SHALL isolate a failing batch from the rest of the run.

#### Scenario: Batch size

- **WHEN** a vectorization request supplies `batch_size`
- **THEN** it must be between 1 and 100, defaulting to 50, and chunks are sent in slices of that size

#### Scenario: Rate-limit response carries Retry-After

- **WHEN** the endpoint responds `429`
- **THEN** it includes a `Retry-After` header derived from the provider's backoff delay

#### Scenario: One batch fails

- **WHEN** a batch's embedding call raises
- **THEN** the chunks in that batch are marked failed, the failure count is incremented, and the remaining batches are still processed

#### Scenario: Partial failure status

- **WHEN** the run finishes with a non-zero failure count
- **THEN** the reported status is `failed` and the result names how many chunks failed, while the successfully embedded chunks remain stored

### Requirement: Embedding Models And Dimensions

The system SHALL support a known set of Azure OpenAI embedding models with fixed vector
dimensions and SHALL reject a request naming an unsupported model.

#### Scenario: Supported models

- **WHEN** the embedding capability is queried
- **THEN** `text-embedding-3-small` (1536 dimensions) and `text-embedding-3-large` (3072 dimensions) are reported

#### Scenario: Unsupported model requested

- **WHEN** a request names a model outside the supported set
- **THEN** an embedding error listing the supported models is raised

#### Scenario: Fake adapter for local development

- **WHEN** `EMBEDDING_USE_FAKE` is true
- **THEN** a deterministic fake embedding adapter is used instead of calling Azure OpenAI

### Requirement: Rate Limit Handling

The system SHALL retry throttled embedding calls with exponential backoff and SHALL
surface an unrecovered rate limit to the caller as `429`.

#### Scenario: Transient throttling

- **WHEN** the provider returns a rate-limit response
- **THEN** the call is retried with exponential backoff bounded by `EMBEDDING_RETRY_DELAY_BASE`, `EMBEDDING_RETRY_DELAY_MAX`, and `EMBEDDING_MAX_RETRIES` (default 5 attempts)

#### Scenario: Rate limit not recovered

- **WHEN** retries are exhausted
- **THEN** the endpoint responds `429 Too Many Requests`

### Requirement: Embedding Payload Contents

The system SHALL store, with each embedding, the vector, the chunk text, and the
searchable metadata needed to populate the vector index without a further SQL lookup.

#### Scenario: Stored embedding

- **WHEN** an embedding is written to blob storage
- **THEN** it carries the `file_id`, `chunk_id`, chunk text, vector, and the document's searchable metadata projection

### Requirement: Stage Event Logging For Vectorization

The system SHALL record a `vectorize` processing event with status and duration for
every vectorization attempt.

#### Scenario: Successful vectorization is recorded

- **WHEN** vectorization completes
- **THEN** a `vectorize` event with status `success`, the elapsed duration, and any partial-failure note is logged

#### Scenario: Failed vectorization is recorded

- **WHEN** vectorization fails
- **THEN** a `vectorize` event with status `failed` and the error message is logged, and unexpected failures also mark the pipeline state failed

### Requirement: Unimplemented Embedding Read Endpoints

The system SHALL reserve the embedding list, read, and delete routes and SHALL report
them as not implemented until they are built.

#### Scenario: Listing, reading, or deleting embeddings

- **WHEN** `GET /api/v1/embeddings`, `GET /api/v1/embeddings/{id}`, or `DELETE /api/v1/embeddings/{id}` is called
- **THEN** the response is `501 Not Implemented`

### Requirement: Embedding Record Invariants

The system SHALL enforce the shape of a stored embedding, so ingestion can validate it
against a collection without re-deriving anything.

#### Scenario: Dimension

- **WHEN** an embedding is created
- **THEN** it records the model used and a vector dimension of at least 1

#### Scenario: Chunk provenance carried

- **WHEN** an embedding is created
- **THEN** it carries the file and chunk identifiers, the chunk text, and metadata recording the model version, token count, chunking strategy, chunk size, overlap, page number, section path, and table flags

#### Scenario: Previews

- **WHEN** an embedding is summarised
- **THEN** the vector preview is its first five components and the text preview the first 100 characters
