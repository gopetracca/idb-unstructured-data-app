# content-extraction Specification

## Purpose

Turn an uploaded source document into machine-readable text. Azure Document
Intelligence analyses the raw blob and produces markdown, the document's structural
elements — tables, figures, paragraphs with roles, sections, and the spans and bounding
regions that locate them — and extraction metadata. That output is stored in the text
container alongside a verbatim copy of the service response, each written under a path
unique to the run that produced it, and the blob references recorded on the document are
the single source of truth for where they live. This is the `convert` stage of the
pipeline.

## Requirements

### Requirement: Extract Content From A Stored Document

The system SHALL extract text from a document already present in the raw container and
store the result as JSON in the text container. The stored result SHALL include the
document's structural elements in addition to the markdown, and SHALL remain readable by
consumers written against the previous output shape.

#### Scenario: Successful extraction

- **WHEN** `POST /api/v1/contents` is called with `documents.write` and a `file_id` whose raw blob exists and whose content type is supported
- **THEN** the document is analysed, the markdown output plus structural elements plus extraction metadata is written under `{tenant_id}/{file_id}/text/` in the output container at a path unique to that run, and the response is `202` carrying `file_id`, `status`, `markdown_url`, `correlation_id`, and `processing_time_ms`

#### Scenario: The core output fields carry the whole extracted text

- **WHEN** a consumer reads `extracted_text`, `pages[].text`, `pages[].word_count`, or `extraction_metadata` and ignores every structural field
- **THEN** it sees the complete extracted text, so a consumer that predates structural preservation needs no change to keep working

#### Scenario: Text output written before structural preservation is still readable

- **WHEN** a text output stored before structural preservation existed is deserialised
- **THEN** it loads successfully and the structural fields default to empty

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

#### Scenario: Fake adapter emits reconstructible structure

- **WHEN** the fake adapter produces output
- **THEN** it includes at least one table with a column-header row and a merged cell, plus paragraphs with roles and per-page lines, so table reconstruction is exercisable without calling Azure

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
### Requirement: Full Analysis Result Preserved

The system SHALL preserve the complete analysis result returned by the extraction service
for every successful extraction, and SHALL NOT discard elements it does not itself consume.

#### Scenario: Raw analysis stored verbatim

- **WHEN** extraction succeeds and `DOCUMENT_INTELLIGENCE_PERSIST_RAW_RESULT` is true
- **THEN** the service response is serialised without filtering and written under
  `{tenant_id}/{file_id}/analysis/` in the output container at a path unique to that run,
  and the document's `analysis_blob_ref` is set to that path before the stage reports
  success

#### Scenario: A run never overwrites another run's raw analysis

- **WHEN** a document that already has a stored raw analysis is extracted again
- **THEN** the new response is written to a different path, and the previous one remains
  readable until the reference has moved past it

#### Scenario: Fields unknown to the domain model survive

- **WHEN** the service response contains a field the domain model does not declare
- **THEN** that field is present in the stored raw analysis

#### Scenario: Raw persistence disabled

- **WHEN** `DOCUMENT_INTELLIGENCE_PERSIST_RAW_RESULT` is false
- **THEN** no raw analysis is written, `analysis_blob_ref` remains null, and the
  structured elements in the text output are still populated in full

#### Scenario: Raw analysis write fails

- **WHEN** writing the raw analysis raises
- **THEN** the failure is logged as a warning, `extraction_metadata.raw_analysis_stored` is
  false, and the extraction result and its `202` response are unchanged

#### Scenario: Text output fails to store after the raw analysis was written

- **WHEN** the raw analysis has been written and the subsequent text-output write fails
- **THEN** the last completed extraction is unchanged — its text output, its raw analysis
  and its blob references all still describe each other — the failed run's raw analysis is
  discarded because nothing references it, and the original failure is the error that
  surfaces

#### Scenario: Recording the references fails

- **WHEN** both outputs have been stored and recording the blob references then fails
- **THEN** the last completed extraction is still published and still matched, this run's
  outputs are discarded because nothing references them, and the failure is reported

#### Scenario: Superseded outputs are not kept

- **WHEN** a re-extraction completes and the references move to its outputs
- **THEN** the text output and raw analysis the references pointed at before are deleted,
  since nothing can reach them any more

#### Scenario: Document extracted before this capability existed

- **WHEN** a document's `analysis_blob_ref` is null
- **THEN** readers treat it as "raw analysis not captured" and no error is raised

### Requirement: Structured Layout Elements In Text Output

The extracted-text output SHALL carry the document's structural elements alongside the
markdown, including tables, figures, paragraphs with their roles, sections, styles,
key-value pairs, and per-page lines, words, and selection marks.

#### Scenario: Tables are structured, not only rendered

- **WHEN** the analysed document contains a table
- **THEN** the text output contains that table as `row_count`, `column_count`, the page numbers
  it appears on, its caption and footnotes when present, and one entry per cell carrying
  `content`, `row_index`, `column_index`, `row_span`, `column_span`, and `kind`

#### Scenario: A table can be reconstructed without the markdown

- **WHEN** a consumer reads a stored table's cells and ignores `extracted_text`
- **THEN** every cell's `(row_index, column_index)` extended by its spans tiles the
  declared `row_count` × `column_count` grid without overlap, so the grid is rebuilt exactly

#### Scenario: Paragraph roles preserved

- **WHEN** the service assigns a paragraph a role such as `title`, `sectionHeading`,
  `pageHeader`, `pageFooter`, or `footnote`
- **THEN** that role is present on the corresponding paragraph in the text output

#### Scenario: Figures and sections preserved

- **WHEN** the analysed document contains figures or a section hierarchy
- **THEN** they appear in the text output with their captions and element references

#### Scenario: Page structure preserved

- **WHEN** a page is analysed
- **THEN** its entry in the text output carries the service's own page number, `width`,
  `height`, `unit`, and `angle`, and its lines, words, and selection marks

#### Scenario: No structural elements found

- **WHEN** the service returns no tables, figures, or key-value pairs
- **THEN** the corresponding fields are present as empty collections and extraction succeeds

### Requirement: Element Offsets And Geometry Preserved

Every preserved element that the service locates SHALL carry its spans into the extracted
markdown and its bounding regions on the page, so elements can be mapped back to both the
text and the page image.

#### Scenario: Spans map an element into the markdown

- **WHEN** a table, paragraph, line, word, or cell is stored
- **THEN** its `spans` are preserved as `(offset, length)` pairs that index into
  `extracted_text`

#### Scenario: Bounding regions map an element onto the page

- **WHEN** an element carries bounding regions
- **THEN** the page number and polygon of each region are preserved

### Requirement: Extraction Metadata Reports Preserved Content

Extraction metadata SHALL report what was preserved, so a document processed before this
capability existed is distinguishable from one processed after.

#### Scenario: Counts recorded

- **WHEN** extraction completes
- **THEN** `extraction_metadata` carries the number of tables, figures, and paragraphs
  preserved, alongside the existing page count, word count, confidence, method, and API
  version

#### Scenario: Raw storage flag recorded

- **WHEN** extraction completes
- **THEN** `extraction_metadata.raw_analysis_stored` states whether the raw analysis was
  written
