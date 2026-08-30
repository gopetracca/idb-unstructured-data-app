# pipeline-orchestration Specification

## Purpose

Drive a document from upload to searchable chunks without blocking the caller. Each
stage runs on its own Azure Storage queue trigger, enqueues the next stage on success,
and records its progress on a per-document pipeline state row. Failures mark the state,
are logged with the correlation id, and are re-raised so the platform's retry and
poison-queue handling applies.

## Requirements

### Requirement: Queue-Driven Pipeline Stages

The system SHALL process documents through a chain of queue-triggered stages, each
consuming one queue and enqueueing the next on success.

#### Scenario: Stage chain

- **WHEN** a document is uploaded
- **THEN** it flows `raw-file` → text extraction → `text-to-chunks` → chunking → `chunk-to-vector` → vectorization → `ingest-to-db` → vector ingestion

#### Scenario: Text extraction trigger

- **WHEN** a message arrives on `raw-to-text`
- **THEN** the document's text is extracted and, on completion, a chunking message is published

#### Scenario: Chunking trigger

- **WHEN** a message arrives on `text-to-chunks`
- **THEN** the document is chunked and, on completion, a vectorization message is published

#### Scenario: Vectorization trigger

- **WHEN** a message arrives on `chunk-to-vector`
- **THEN** the document's chunks are vectorized and, on completion, an ingestion message is published

#### Scenario: Ingestion trigger

- **WHEN** a message arrives on `ingest-to-db`
- **THEN** the document's embeddings are loaded from blob storage and upserted into the collection

### Requirement: Stage Chaining Is Conditional On Success

The system SHALL enqueue the next stage only when the current stage reports completion,
and SHALL NOT fail the current stage when the enqueue itself fails.

#### Scenario: Stage did not complete

- **WHEN** a stage finishes with a status other than completed
- **THEN** a warning is logged and no message is published for the next stage

#### Scenario: Enqueue failure

- **WHEN** publishing the next stage's message raises
- **THEN** the error is logged and the completed stage's result is still returned

#### Scenario: No collection assigned

- **WHEN** vectorization completes for a document with no `collection_name`
- **THEN** a warning is logged and no ingestion message is published

### Requirement: Queue Message Envelope

The system SHALL wrap every pipeline message in a standard envelope carrying tenant,
file, version, operation, correlation, timestamp, retry count, a stage-specific payload,
and distributed trace context.

#### Scenario: Envelope fields

- **WHEN** a message is published
- **THEN** it carries `tenantId`, `fileId`, `fileVersion`, `operationId`, `correlationId`, `timestamp`, `retryCount`, `payload`, and `_datadog` trace headers

#### Scenario: Correlation id propagation

- **WHEN** a stage enqueues the next one
- **THEN** the current stage's correlation id is carried forward rather than a new one being minted

#### Scenario: File version resolution

- **WHEN** a message is built and the file version is not supplied
- **THEN** it is read from the document record, defaulting to 1 when the document cannot be found

#### Scenario: Unparseable message

- **WHEN** a queue message is not valid JSON or does not match the envelope shape
- **THEN** parsing raises a value error naming the problem

### Requirement: Stage Payload Contents

The system SHALL carry each stage's container and configuration choices in the message
payload, with the consumer falling back to configured defaults when a field is absent.

#### Scenario: Chunking payload

- **WHEN** a chunking message is published
- **THEN** it carries `source_container`, `output_container`, and the document's chunking strategy

#### Scenario: Ingestion payload

- **WHEN** an ingestion message is published
- **THEN** it carries `source_container`, `collection_name`, and `batch_size`

#### Scenario: Payload defaults

- **WHEN** a consumer finds no container in the payload
- **THEN** the corresponding configured container name is used

#### Scenario: Chunking strategy default

- **WHEN** a chunking message carries no strategy
- **THEN** fixed-size chunking is applied

### Requirement: Pipeline State Tracking

The system SHALL maintain one pipeline state row per document recording its current
stage, overall status, chunk counts, last error, retry count, and pipeline configuration.

#### Scenario: Stages

- **WHEN** a document is processed
- **THEN** its current stage is one of `dispatcher`, `convert`, `chunk`, `vectorize`, `ingest`, or `completed`

#### Scenario: Overall status

- **WHEN** a document's status is read
- **THEN** it is one of `queued`, `processing`, `completed`, or `failed`

#### Scenario: Marking processing

- **WHEN** a stage begins
- **THEN** the state moves to that stage with status `processing` and its last-updated timestamp is refreshed

#### Scenario: Marking completed

- **WHEN** ingestion succeeds for every embedding
- **THEN** the state moves to stage `completed` with status `completed`

#### Scenario: Marking failed

- **WHEN** a stage fails
- **THEN** the state's status becomes `failed`, the error message is recorded, and the retry count is incremented

#### Scenario: Chunk counters

- **WHEN** chunking and vectorization complete
- **THEN** the chunk count and embedded chunk count are recorded on the state

### Requirement: Queue Trigger Error Handling

The system SHALL handle stage failures uniformly: record the failure on the pipeline
state, log it with the message's identifiers, and re-raise so the platform retries.

#### Scenario: Stage raises

- **WHEN** a stage operation raises
- **THEN** the error is logged with `file_id`, `tenant_id`, and `correlation_id`, the pipeline state is marked failed, and the exception is re-raised

#### Scenario: State update also fails

- **WHEN** marking the pipeline state failed itself raises
- **THEN** that secondary failure is logged and the original exception is still re-raised

#### Scenario: Platform retry and poison handling

- **WHEN** a message is re-raised
- **THEN** the Azure Functions queue host retries it up to the configured dequeue limit and then moves it to the poison queue

### Requirement: Queue Host Configuration

The system SHALL configure the queue host for bounded concurrency and bounded retries.

#### Scenario: Queue settings

- **WHEN** the Functions host reads its configuration
- **THEN** queue messages are base64-encoded, polled at most every 5 seconds, held invisible for 5 minutes, processed in batches of 4, and dequeued at most twice before going to the poison queue

### Requirement: Best-Effort Storage Provisioning At Startup

The system SHALL attempt to create the blob containers and queues the pipeline depends
on at startup, and SHALL treat the attempt as best-effort: provisioning is deliberately
not a precondition for serving traffic, so a failure to create or reach a resource
degrades the pipeline at request time rather than preventing the application from
starting.

#### Scenario: Startup initialization

- **WHEN** the application starts
- **THEN** creation is attempted for the raw, text, chunks, and embeddings containers and for the `raw-file`, `raw-to-text`, `text-to-chunks`, `chunk-to-vector`, `ingest-to-db`, and `delete-file` queues

#### Scenario: Provisioning failure does not abort startup

- **WHEN** creating a container or queue fails for any reason — the resource already exists, the credential is unauthorized, or the storage account is unreachable
- **THEN** the failure is swallowed, startup continues, and the application begins serving traffic

#### Scenario: Success is not distinguished from failure

- **WHEN** a creation call raises
- **THEN** the outcome is reported as "not created", which is the same outcome reported when the resource already existed
- **AND** the startup log line stating the resource was ensured is therefore not evidence that it exists

#### Scenario: Missing container surfaces at upload time

- **WHEN** a container does not exist and a document is uploaded
- **THEN** the blob write fails and the request returns `500` with error `StorageError`

#### Scenario: Missing queue silently strands the document

- **WHEN** a pipeline queue does not exist and a document is uploaded
- **THEN** the upload still returns `201` because enqueue failures are logged rather than raised, leaving the document persisted in blob storage and SQL but never processed
- **AND** the document's pipeline state stays at stage `dispatcher` with status `queued`

### Requirement: Synchronous Stage Endpoints

The system SHALL also expose each pipeline stage as a directly invocable HTTP endpoint,
so a stage can be re-run or driven manually.

#### Scenario: Manual stage invocation

- **WHEN** `POST /api/v1/contents`, `POST /api/v1/chunks`, or `POST /api/v1/embeddings` is called with `documents.write`
- **THEN** that stage runs for the named document and returns `202` with its result, independently of the queue chain
