# content-extraction Delta

## ADDED Requirements

### Requirement: Selectable Extraction Engine

The system SHALL select the extraction engine from `EXTRACTION_ADAPTER`, SHALL default to
Azure Document Intelligence, and SHALL fail at startup on an unrecognised value rather than
choosing an engine by default.

#### Scenario: Default engine

- **WHEN** `EXTRACTION_ADAPTER` is unset
- **THEN** Azure Document Intelligence is used and extraction behaviour is unchanged

#### Scenario: Docling selected

- **WHEN** `EXTRACTION_ADAPTER` is `docling`
- **THEN** extraction runs in-process with Docling, no request is made to Azure Document Intelligence, and the document bytes do not leave the container

#### Scenario: Unrecognised engine

- **WHEN** `EXTRACTION_ADAPTER` is set to any value other than `document_intelligence`, `docling`, or the fake selector
- **THEN** startup fails with an error naming `EXTRACTION_ADAPTER` and the values it accepts

#### Scenario: Docling is never an implicit fallback

- **WHEN** `DOCUMENT_INTELLIGENCE_ENDPOINT` is empty and `EXTRACTION_ADAPTER` is not `docling`
- **THEN** the existing fake-adapter fallback applies unchanged, and Docling is not substituted, because a missing Azure endpoint is no evidence that Docling model artifacts are present

### Requirement: Engine-Independent Extraction Output

Every extraction engine SHALL produce the same `text.json` contract, and SHALL leave
unavailable fields empty rather than approximating them.

#### Scenario: Contract satisfied by Docling

- **WHEN** Docling extracts a document
- **THEN** the run's text output carries `extracted_text`, per-page text, word counts and geometry, tables with cell row/column indices and header flags, figures, paragraphs with roles, sections, and per-item bounding regions, in the same shape the Azure adapter produces

#### Scenario: Chunking is unaffected by the engine

- **WHEN** the chunking stage reads a text output produced by Docling, located through the document's `text_blob_ref`
- **THEN** it reads `extracted_text` and chunks successfully, with no engine-specific handling

#### Scenario: Fields with no engine equivalent

- **WHEN** the engine has no equivalent for a field — markdown character spans and per-word confidence for Docling, for example
- **THEN** the field is empty or unset, and no substitute value is synthesised

#### Scenario: Bounding regions normalised

- **WHEN** an engine reports page geometry in a different coordinate origin or unit than the stored contract declares
- **THEN** the values are converted to the contract's convention and the unit is recorded, so regions from different engines are directly comparable

### Requirement: Extraction Output Identifies Its Engine

Stored extraction output SHALL record which engine produced it and which schema its raw
analysis uses, so a mixed corpus is unambiguous.

#### Scenario: Engine recorded

- **WHEN** extraction succeeds
- **THEN** `extraction_metadata.extraction_method` names the engine that ran, not a fixed default

#### Scenario: Raw analysis schema recorded

- **WHEN** a raw analysis artifact is stored for a run
- **THEN** `extraction_metadata.analysis_format` names its schema, and a reader determines the schema from that value rather than from the blob path or by inspecting the payload

#### Scenario: Docling raw analysis

- **WHEN** Docling extracts a document and raw persistence is enabled
- **THEN** the serialised `DoclingDocument` is written to the run-scoped analysis path, published to `analysis_blob_ref` in the same update as the text reference, and `analysis_format` is `docling-document`

#### Scenario: Output predating engine tagging

- **WHEN** a text output has no `analysis_format`
- **THEN** it is read as Azure Document Intelligence output and no error is raised

### Requirement: Engine Choice Does Not Weaken Output Publication

A new extraction engine SHALL use the existing run-scoped write and atomic publication
contract unchanged, and SHALL NOT introduce a path any reader is expected to guess.

#### Scenario: Outputs are run-scoped

- **WHEN** any engine writes its text output and raw analysis
- **THEN** both are written under paths unique to that run, so a concurrent extraction of the same document cannot overwrite what another run published

#### Scenario: References are the only locator

- **WHEN** a reader locates a document's text output or raw analysis
- **THEN** it follows `text_blob_ref` and `analysis_blob_ref` on the document row, and no path is reconstructed by convention

#### Scenario: The pair is published together

- **WHEN** a run publishes its outputs
- **THEN** both references move in one update, so the row never holds a text output from one run beside a raw analysis from another, whichever engine produced them

#### Scenario: A failed or terminated run publishes nothing

- **WHEN** a conversion fails, times out, or is terminated at its hard deadline
- **THEN** nothing is published, only that run's own outputs are discarded, and the previously published pair remains referenced and intact

### Requirement: In-Process Conversion Is Terminable

In-process extraction SHALL run where it can be forcibly terminated, and the system SHALL
guarantee that a conversion has stopped consuming CPU before the queue can redeliver its
message. Cancelling an awaitable SHALL NOT be relied on as the termination mechanism.

#### Scenario: Hard deadline terminates the work

- **WHEN** a conversion is still running at its hard deadline
- **THEN** the execution context running it is killed, its CPU and memory are reclaimed, and the `convert` stage is marked failed with reason `conversion_timeout`

#### Scenario: Termination does not depend on the conversion cooperating

- **WHEN** a conversion is inside an operation that never checks for cancellation, such as a single model inference
- **THEN** it is still terminated at the hard deadline, so the guarantee does not rest on the conversion library yielding control

#### Scenario: No overlap with a redelivered message

- **WHEN** the hard deadline is configured
- **THEN** it leaves enough of the queue visibility timeout for the stage's remaining work — the run-scoped analysis and text writes, the reference publication, and the sweep of what it displaced — to finish, so no conversion is ever running at the moment its own message becomes visible again

#### Scenario: Termination is proven, not assumed

- **WHEN** the termination path is tested
- **THEN** a conversion that ignores cooperative cancellation is shown to have actually stopped within the deadline, rather than the test only asserting that the awaiting call returned

#### Scenario: A killed conversion does not take the worker with it

- **WHEN** a conversion is terminated, or dies on its own from memory exhaustion
- **THEN** the trigger records the stage failure and the worker continues serving health probes and subsequent messages

### Requirement: Layered Conversion Limits

The system SHALL reject work it cannot finish before starting it, and SHALL bound work in
progress, so that forced termination is the last resort rather than the normal path.

#### Scenario: Document too large to attempt

- **WHEN** a document exceeds `DOCLING_MAX_PAGES` or the configured maximum file size
- **THEN** the stage fails immediately with reason `page_limit_exceeded` or `file_size_limit_exceeded`, before conversion starts

#### Scenario: Cooperative timeout bounds overshoot

- **WHEN** a conversion exceeds the engine's own document timeout
- **THEN** the engine stops at its next checkpoint and the stage fails with reason `conversion_timeout`, without waiting for the hard deadline

#### Scenario: Cooperative timeout is set below the hard deadline

- **WHEN** both limits are configured
- **THEN** the engine's own timeout is the shorter, so the ordinary slow document ends cooperatively and forced termination is reserved for the case where that fails

#### Scenario: Partial results are not stored as complete

- **WHEN** a conversion reports partial success because a limit was reached
- **THEN** the stage fails and publishes nothing, so no document is silently indexed on incomplete text and the previously published pair stays current

#### Scenario: Concurrency is bounded by memory, not by the queue

- **WHEN** conversions run concurrently
- **THEN** the number in flight is limited by configuration sized against per-conversion memory, independently of the queue batch size

### Requirement: Docling Supported Formats

When Docling is the configured engine, the system SHALL report Docling's own accepted
content types.

#### Scenario: Formats follow the engine

- **WHEN** `GET /documents/supported-formats` or `GET /api/v1/capabilities` is called while `EXTRACTION_ADAPTER` is `docling`
- **THEN** the response lists the content types Docling accepts, which differ from the Azure adapter's list

#### Scenario: Format rejected by the configured engine

- **WHEN** a document's content type is accepted by one engine but not the configured one
- **THEN** the response is `400` naming the content type and the configured engine's supported formats, as for any unsupported format
