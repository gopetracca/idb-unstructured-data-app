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
- **THEN** `text.json` carries `extracted_text`, per-page text, word counts and geometry, tables with cell row/column indices and header flags, figures, paragraphs with roles, sections, and per-item bounding regions, in the same shape the Azure adapter produces

#### Scenario: Chunking is unaffected by the engine

- **WHEN** the chunking stage reads a `text.json` produced by Docling
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

- **WHEN** a raw analysis artifact is stored at `{tenant_id}/{file_id}/analysis.json`
- **THEN** `extraction_metadata.analysis_format` names its schema, and a reader determines the schema from that value rather than from the blob path or by inspecting the payload

#### Scenario: Docling raw analysis

- **WHEN** Docling extracts a document and raw persistence is enabled
- **THEN** the serialised `DoclingDocument` is written to `{tenant_id}/{file_id}/analysis.json`, `analysis_blob_ref` is recorded, and `analysis_format` is `docling-document`

#### Scenario: Output predating engine tagging

- **WHEN** a `text.json` has no `analysis_format`
- **THEN** it is read as Azure Document Intelligence output and no error is raised

### Requirement: Bounded In-Process Conversion

In-process extraction SHALL be bounded so that it cannot outlive the queue message
visibility timeout, and SHALL fail with a stated reason rather than run past its deadline.

#### Scenario: Conversion exceeds its budget

- **WHEN** a Docling conversion runs longer than `DOCLING_CONVERSION_TIMEOUT_SECONDS`
- **THEN** it is abandoned, the `convert` stage is marked failed with reason `conversion_timeout`, and the message is not left running past the point where the queue makes it visible again

#### Scenario: Timeout stays inside the visibility window

- **WHEN** the conversion timeout is configured
- **THEN** its default is below the queue visibility timeout, so a timed-out conversion fails before the same message can be redelivered to a second worker

#### Scenario: Document too large to attempt

- **WHEN** a document exceeds `DOCLING_MAX_PAGES`
- **THEN** the stage fails immediately with reason `page_limit_exceeded` and the page count, before conversion starts

#### Scenario: Conversion does not block the worker

- **WHEN** a conversion runs
- **THEN** it executes off the event loop under a bounded concurrency limit, so health probes and other triggers on the same worker continue to be served

### Requirement: Docling Supported Formats

When Docling is the configured engine, the system SHALL report Docling's own accepted
content types.

#### Scenario: Formats follow the engine

- **WHEN** `GET /documents/supported-formats` or `GET /api/v1/capabilities` is called while `EXTRACTION_ADAPTER` is `docling`
- **THEN** the response lists the content types Docling accepts, which differ from the Azure adapter's list

#### Scenario: Format rejected by the configured engine

- **WHEN** a document's content type is accepted by one engine but not the configured one
- **THEN** the response is `400` naming the content type and the configured engine's supported formats, as for any unsupported format
