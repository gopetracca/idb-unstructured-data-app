# vector-ingestion Specification

## Purpose

Load a document's embeddings into a vector collection so they become searchable. This is
the `ingest` stage of the pipeline: it validates vector dimensions against the target
collection, assembles the typed searchable metadata each indexed chunk carries, and
upserts the batch, reporting per-document success and failure.

## Requirements

### Requirement: Ingest Vectorized Documents Into A Collection

The system SHALL upsert a batch of vectorized chunks into a named collection and SHALL
report totals for successful and failed documents.

#### Scenario: Successful ingestion

- **WHEN** `POST /api/v1/collections/{collection_name}/documents` is called with `admin` and a batch of vectorized documents
- **THEN** the documents are upserted and the response carries `total_documents`, `successful`, `failed`, `failed_ids`, `processing_time_ms`, and the correlation id

#### Scenario: Unknown collection

- **WHEN** the named collection does not exist
- **THEN** an index-not-found error is raised and the response is `404`

#### Scenario: Partial upsert

- **WHEN** the vector database accepts only some of the documents
- **THEN** the failed ids are computed as the difference between the submitted and the accepted ids and reported in the response

#### Scenario: Ingestion failure

- **WHEN** the upsert itself raises
- **THEN** a vector database error naming the collection is raised and the response is `500`

### Requirement: Vector Dimension Validation

The system SHALL validate every submitted vector against the target collection's
declared dimension before attempting any upsert.

#### Scenario: Mismatched dimension

- **WHEN** any submitted vector's length differs from the collection's `vector_dimension`
- **THEN** a vector dimension mismatch error naming the expected and actual dimensions is raised and nothing is upserted

#### Scenario: Error message bounds the detail

- **WHEN** more than five documents have the wrong dimension
- **THEN** the error message names the first five and states how many more there are

### Requirement: Searchable Metadata Assembly

The system SHALL assemble each indexed chunk's searchable metadata from the document's
SQL metadata plus the chunk's own positional metadata, so search results are citable
without a follow-up database lookup.

#### Scenario: Metadata joined at ingestion

- **WHEN** documents are transformed for upsert
- **THEN** each vector document carries a typed searchable metadata projection combining the document-level fields and the chunk-level fields

#### Scenario: Fields unsupported by the index schema are dropped

- **WHEN** an embedding's metadata carries fields the index schema does not define
- **THEN** those fields are filtered out before upsert rather than failing the batch

### Requirement: Pipeline Completion On Ingestion

The system SHALL mark a document's pipeline complete when all of its embeddings ingest
successfully, and failed when any of them do not.

#### Scenario: All documents ingested

- **WHEN** the ingest queue trigger finishes with zero failures for a file
- **THEN** the document's pipeline state is marked completed

#### Scenario: Some documents failed

- **WHEN** the ingest queue trigger finishes with a non-zero failure count
- **THEN** the document's pipeline state is marked failed with a message naming how many of how many failed

#### Scenario: No embeddings found

- **WHEN** the ingest trigger finds no embedding blobs for the file
- **THEN** a warning is logged and the stage exits without marking the document complete

#### Scenario: Collection name required

- **WHEN** an ingest queue message omits `collection_name`
- **THEN** the message fails with an error rather than defaulting to an arbitrary collection

### Requirement: Stage Event Logging For Ingestion

The system SHALL record an `ingest` processing event per file covered by an ingestion
batch, carrying the duration and any failure detail.

#### Scenario: Ingestion recorded per file

- **WHEN** a batch spanning several files is ingested
- **THEN** one `ingest` event is recorded for each distinct `file_id` in the batch

### Requirement: Vector Document Invariants

The system SHALL reject a vector document that cannot be indexed coherently, before it
reaches the vector database.

#### Scenario: Empty vector

- **WHEN** a vector document is constructed with an empty vector
- **THEN** construction fails

#### Scenario: Composite identifier

- **WHEN** a vector document identifier is supplied
- **THEN** it must follow the `{file_id}_{chunk_id}` composite pattern, so a chunk is unique across files within one index
