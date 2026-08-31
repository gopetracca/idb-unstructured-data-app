# content-extraction Delta

Rebased onto the `provider-neutral-extraction-model` specs now merged into
`openspec/specs/content-extraction/spec.md`. Requirements that baseline already states —
blocks in reading order resolving against the text whoever produced the offsets, geometry
carrying its unit and origin, canonical cell roles, derived header rows, fragment
composition, and the run-scoped write with its atomic publication and cleanup — are **not**
restated here. A delta that repeats the baseline creates a second source of truth that can
only drift from it.

What is left is what a second engine actually changes.

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

#### Scenario: Chunking is unaffected by the engine

- **WHEN** the chunking stage reads a text output produced by Docling, located through the document's `text_blob_ref`
- **THEN** it reads `extracted_text` and chunks successfully, with no engine-specific handling

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

### Requirement: Engine Capability Differences Are Recorded, Not Repaired

Where engines differ in what they can report, the system SHALL record the difference and
SHALL NOT synthesise the missing part. An adapter SHALL NOT repair its engine's output into
a shape another engine guarantees.

#### Scenario: Fields with no engine equivalent

- **WHEN** the engine has no equivalent for a field — provider-reported character spans, visual styles, key-value pairs and a confidence probability, for Docling
- **THEN** the field is empty or unset, and no substitute value is synthesised

#### Scenario: A confidence grade is not a confidence score

- **WHEN** an engine reports document quality as a coarse grade rather than a probability
- **THEN** `extraction_confidence` is left at its default rather than mapped onto the scale, because a derived number is indistinguishable from a measured one

#### Scenario: An engine's structural imperfection is not corrected

- **WHEN** an engine reports a table whose cells overlap or leave declared positions uncovered
- **THEN** the cells are stored exactly as reported, because a repaired grid would be indistinguishable from a read one and no consumer could tell which it held

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

## MODIFIED Requirements

### Requirement: Structured Layout Elements In Text Output

The extracted-text output SHALL carry the document's structural elements alongside the
markdown — tables, figures, paragraphs with their roles, sections, styles, key-value
pairs, and per-page lines, words, and selection marks — and SHALL carry the canonical
block list required by *Provider-Neutral Extraction Output*.

#### Scenario: Tables are structured, not only rendered

- **WHEN** the analysed document contains a table
- **THEN** `text.json` contains that table as `row_count`, `column_count`, the page numbers
  it appears on, its caption and footnotes when present, and one entry per cell carrying
  `content`, `row_index`, `column_index`, `row_span`, `column_span`, and its canonical role

#### Scenario: A table can be reconstructed without the markdown

- **WHEN** a consumer reads a stored table's cells and ignores `extracted_text`
- **THEN** the cells are rebuilt into a `row_count` × `column_count` grid from
  `(row_index, column_index)` and the spans alone, with no reference to the rendering

#### Scenario: An engine that guarantees a clean grid

- **WHEN** Azure Document Intelligence produced the table
- **THEN** every cell extended by its spans tiles the declared grid exactly once, with no
  overlap and no uncovered position

#### Scenario: An engine that does not

- **WHEN** an engine's table model reports cells that overlap, or leaves declared positions
  covered by no cell — as Docling's does on nested headers in real documents
- **THEN** the cells are stored as reported, the reconstruction resolves a contested
  position to one of the cells claiming it and leaves an uncovered position empty, and
  extraction succeeds
- **AND** a consumer that requires an exact tiling checks for it rather than assuming it
  holds across engines

#### Scenario: Paragraph roles preserved

- **WHEN** the service assigns a paragraph a role such as title, section heading, page
  header, page footer, or footnote
- **THEN** that role is preserved on the corresponding paragraph exactly as the service
  spelled it, and no requirement depends on its vocabulary — what an element *is*, said
  canonically, is its block's kind

#### Scenario: Figures and sections preserved

- **WHEN** the analysed document contains figures or a section hierarchy
- **THEN** they appear in `text.json` with their captions and element references

#### Scenario: Page structure preserved

- **WHEN** a page is analysed
- **THEN** its entry in `text.json` carries the service's own page number, `width`,
  `height`, `unit`, and `angle`, and its lines, words, and selection marks

#### Scenario: No structural elements found

- **WHEN** the service returns no tables, figures, or key-value pairs
- **THEN** the corresponding fields are present as empty collections and extraction succeeds

#### Scenario: A stored output that carries no block list

- **WHEN** a `text.json` that has no block list is read
- **THEN** it deserialises with an empty block list, and consumers treat that as structure
  being unavailable rather than as a document with no structure

### Requirement: Supported Extraction Formats

The system SHALL expose the set of content types the extraction adapter accepts, and
SHALL accept PDF, DOCX, PNG, JPEG, TIFF, BMP, and plain text by default. The set SHALL
follow the configured engine rather than being fixed.

#### Scenario: Querying supported formats

- **WHEN** `GET /documents/supported-formats` is called with `documents.read`
- **THEN** the response lists the content types the configured adapter supports

#### Scenario: Formats follow the engine

- **WHEN** `EXTRACTION_ADAPTER` is `docling`
- **THEN** the response lists the content types Docling accepts, which include presentations, spreadsheets, HTML and Markdown that Document Intelligence does not

#### Scenario: Format rejected by the configured engine

- **WHEN** a document's content type is accepted by one engine but not the configured one
- **THEN** the response is `400` naming the content type and the configured engine's supported formats, as for any unsupported format

#### Scenario: Fake adapter for local development

- **WHEN** `DOCUMENT_INTELLIGENCE_USE_FAKE` is true
- **THEN** a fake adapter produces deterministic output after a simulated delay instead of calling Azure

#### Scenario: Fake adapter emits reconstructible structure

- **WHEN** the fake adapter produces output
- **THEN** it includes at least one table with a column-header row and a merged cell, plus paragraphs with roles and per-page lines, so table reconstruction is exercisable without calling Azure
