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

- **WHEN** `EXTRACTION_ADAPTER` is set to any value other than `document_intelligence` or `docling`
- **THEN** startup fails with an error naming `EXTRACTION_ADAPTER` and the values it accepts

#### Scenario: Docling is never an implicit fallback

- **WHEN** `DOCUMENT_INTELLIGENCE_ENDPOINT` is empty and `EXTRACTION_ADAPTER` is not `docling`
- **THEN** the existing fake-adapter fallback applies unchanged, and Docling is not substituted, because a missing Azure endpoint is no evidence that Docling model artifacts are present

### Requirement: Every Engine Satisfies The Same Canonical Contract

Every extraction engine SHALL produce output that satisfies the canonical extraction
contract in full, and SHALL leave what it cannot fill empty rather than approximating it.

#### Scenario: Contract satisfied by Docling

- **WHEN** Docling extracts a document
- **THEN** the run's text output carries blocks in reading order whose ranges resolve against `extracted_text`, tables with canonical cell roles and header rows derived from those cells, figures, paragraphs with the engine's own role preserved, per-page geometry, and bounding boxes — in the same shape the Azure adapter produces

#### Scenario: The adapter renders when its engine reports no offsets

- **WHEN** an engine returns a document tree rather than a rendered string
- **THEN** the adapter renders the text itself and records each element's range as it writes, rather than searching a rendering for the text that produced it

#### Scenario: A table's parts are exactly its whole, whichever markup it is in

- **WHEN** an engine renders tables in a form the other does not
- **THEN** the adapter partitions the rendering it produced into a prefix, body rows and a suffix, so a consumer composes a fragment by concatenation alone and never learns which form it got

#### Scenario: Chunking is unaffected by the engine

- **WHEN** the chunking stage reads a text output produced by Docling, located through the document's `text_blob_ref`
- **THEN** it reads `extracted_text` and chunks successfully, with no engine-specific handling

#### Scenario: Fields with no engine equivalent

- **WHEN** the engine has no equivalent for a field — character spans, visual styles, key-value pairs and a confidence probability, for Docling
- **THEN** the field is empty or unset, and no substitute value is synthesised

#### Scenario: Geometry is labelled, not converted

- **WHEN** an engine reports page geometry in a different coordinate origin or unit than another engine does
- **THEN** the values are stored as reported, with their unit and origin recorded, so that a consumer comparing geometry across engines can see the difference rather than have it silently converted away

### Requirement: Extraction Output Identifies Its Engine

Stored extraction output SHALL record which engine produced it and which schema its raw
analysis uses, so a mixed corpus is unambiguous.

#### Scenario: Engine recorded

- **WHEN** extraction succeeds
- **THEN** `extraction_metadata.extraction_method` names the engine that ran, and `api_version` the version of that engine, rather than a fixed default

#### Scenario: Raw analysis schema recorded

- **WHEN** a raw analysis artifact is stored for a run
- **THEN** `extraction_metadata.analysis_format` names its schema, and a reader determines the schema from that value rather than from the blob path or by inspecting the payload

#### Scenario: Docling raw analysis

- **WHEN** Docling extracts a document and raw persistence is enabled
- **THEN** the serialised `DoclingDocument` is written to the run-scoped analysis path, published to `analysis_blob_ref` in the same update as the text reference, and `analysis_format` is `docling-document`

#### Scenario: Output predating engine tagging

- **WHEN** a text output has no `analysis_format`
- **THEN** it is read as Azure Document Intelligence output and no error is raised

### Requirement: Raw-Analysis Persistence Is Engine-Neutral

Whether a run's verbatim engine response is stored SHALL be a property of the extraction
stage rather than of any one engine, and existing deployed configuration SHALL keep
working.

#### Scenario: Engine-neutral setting governs

- **WHEN** `PERSIST_RAW_EXTRACTION` is set
- **THEN** it decides whether the sidecar is written, whichever engine ran

#### Scenario: The existing name is still honoured

- **WHEN** `PERSIST_RAW_EXTRACTION` is unset and `DOCUMENT_INTELLIGENCE_PERSIST_RAW_RESULT` is set
- **THEN** the latter still governs, because that is the name deployed configuration already uses

#### Scenario: Both set

- **WHEN** both are set and they disagree
- **THEN** the engine-neutral setting wins

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

#### Scenario: A failed run publishes nothing

- **WHEN** a conversion fails or is cut short
- **THEN** nothing is published, only that run's own outputs are discarded, and the previously published pair remains referenced and intact

### Requirement: Layered Conversion Limits

In-process extraction SHALL reject work it cannot finish before starting it, and SHALL
bound the conversion once started. The system SHALL state which of those limits is a
guarantee and which is not.

#### Scenario: Document too large to attempt

- **WHEN** a document exceeds the configured maximum file size
- **THEN** the stage fails immediately with reason `file_size_limit_exceeded`, before conversion starts and before any model runs

#### Scenario: Page limit applied as the document is opened

- **WHEN** a document exceeds `DOCLING_MAX_PAGES`
- **THEN** the conversion does not complete and the stage fails, rather than the document being converted and truncated

#### Scenario: Cooperative timeout bounds overshoot

- **WHEN** a conversion exceeds the engine's own document timeout
- **THEN** the engine stops at its next checkpoint and the stage fails

#### Scenario: The cooperative bound is not presented as a guarantee

- **WHEN** a conversion is inside an operation that never checks for cancellation, such as a single model inference
- **THEN** the timeout does not stop it, and this is documented rather than implied otherwise — a hard deadline requires an execution context that can be killed, which is deferred

#### Scenario: Partial results are not stored as complete

- **WHEN** a conversion reports partial success because a limit was reached
- **THEN** the stage fails and publishes nothing, so no document is silently indexed on incomplete text and the previously published pair stays current

#### Scenario: The event loop keeps serving

- **WHEN** a CPU-bound conversion is in progress
- **THEN** it runs off the event loop, so the worker continues answering health probes

### Requirement: Docling Supported Formats

When Docling is the configured engine, the system SHALL report Docling's own accepted
content types.

#### Scenario: Formats follow the engine

- **WHEN** `GET /documents/supported-formats` or `GET /api/v1/capabilities` is called while `EXTRACTION_ADAPTER` is `docling`
- **THEN** the response lists the content types Docling accepts, which differ from the Azure adapter's list

#### Scenario: Format rejected by the configured engine

- **WHEN** a document's content type is accepted by one engine but not the configured one
- **THEN** the response is `400` naming the content type and the configured engine's supported formats, as for any unsupported format
