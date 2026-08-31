# content-extraction Specification

## Purpose

Turn an uploaded source document into machine-readable text. An extraction service —
Azure Document Intelligence today — analyses the raw blob, and the stage emits the result
in a canonical form: the rendered text, the document's blocks in reading order, its
structural elements (tables with their cell grid, figures, paragraphs with roles,
sections) and the offsets and geometry that locate them, plus extraction metadata. The
canonical form names no service, so which extractor ran is a deployment fact rather than
something a consumer can observe. That output is stored in the text container alongside a
verbatim copy of the service response, each written under a path unique to the run that
produced it, and the blob references recorded on the document are the single source of
truth for where they live. This is the `convert` stage of the pipeline.

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
  cleaned up on a best-effort basis because nothing references it, and the original failure
  is the error that surfaces

#### Scenario: Recording the references fails

- **WHEN** both outputs have been stored and recording the blob references then fails
- **THEN** the last completed extraction is still published and still matched, this run's
  outputs are cleaned up on a best-effort basis because nothing references them, and the
  failure is reported

#### Scenario: Superseded outputs are cleaned up

- **WHEN** a re-extraction completes and the references move to its outputs
- **THEN** deletion of the text output and raw analysis the references pointed at before is
  attempted, since nothing can reach them any more

#### Scenario: Cleaning up a superseded or abandoned output fails

- **WHEN** deleting an output that nothing references raises
- **THEN** the failure is logged as a warning and neither the extraction result nor the
  published references change, because the blob is already unreachable — deleting it
  reclaims storage rather than protecting a reader — and a document deletion later sweeps
  it by prefix

#### Scenario: Document extracted before this capability existed

- **WHEN** a document's `analysis_blob_ref` is null
- **THEN** readers treat it as "raw analysis not captured" and no error is raised

### Requirement: Provider-Neutral Extraction Output

The extraction stage SHALL emit its result in a canonical form that identifies the
document's structure without reference to the service that produced it, so that consumers
need no knowledge of which extractor ran.

#### Scenario: Blocks in reading order

- **WHEN** a document is extracted
- **THEN** the output carries the document's blocks in reading order, each declaring its
  kind — heading, paragraph, table, figure, caption, or list item — and each carrying the
  character range it occupies in the extracted text

#### Scenario: Every block resolves against the extracted text

- **WHEN** a consumer reads a block's character range
- **THEN** that range indexes into `extracted_text` and yields that block's text, whether
  the extraction service supplied the offsets or the adapter produced them while rendering

#### Scenario: Page attribution

- **WHEN** the extraction service reports which page an element is on
- **THEN** the corresponding block carries that page number

#### Scenario: Geometry carries its units

- **WHEN** a block carries a bounding box
- **THEN** the box declares its unit and its coordinate origin, and no consumer is required
  to infer either

#### Scenario: Provider references are preserved but not interpreted

- **WHEN** the extraction service links an element to other elements
- **THEN** those references are preserved verbatim, and no requirement depends on their
  format

### Requirement: Normalised Table Structure

Tables SHALL be described in canonical terms — cell positions, spans, and roles — that
are the same regardless of which service produced them.

#### Scenario: Cell roles are canonical

- **WHEN** the extraction service marks a cell as a column header, a row header, a section
  row, or a stub head
- **THEN** the stored cell carries the canonical role for it, not the service's own
  spelling

#### Scenario: Header rows identified

- **WHEN** a table has header cells
- **THEN** the table declares which row indices form its header, derived from the cell
  roles rather than assumed to be the first row

#### Scenario: A table with no header

- **WHEN** no cell in a table is marked as a header
- **THEN** the table's header rows are empty and extraction succeeds

#### Scenario: Table text is provided, not derived

- **WHEN** a consumer needs a table's text
- **THEN** it is available as a string the extractor produced, in the same form it takes in
  `extracted_text`, so that no consumer parses the rendering to recover it

#### Scenario: Fragment composition is defined once

- **WHEN** a consumer needs some rows of a table
- **THEN** the fragment for a selection of body rows is exactly
  `render_prefix` + those rows' renderings in document order + `render_suffix`, and this
  concatenation is the only operation a consumer performs to obtain it

#### Scenario: Every fragment is valid in the extractor's form

- **WHEN** a fragment is composed for any selection of body rows
- **THEN** it is a valid table in the form the extractor produced, because `render_prefix`
  is exactly the part of the rendering that precedes the first body row — whatever that
  form requires there — and `render_suffix` is exactly the part that follows the last

#### Scenario: A form that requires a header line

- **WHEN** the extractor renders tables in a form that cannot express a table without a
  header line, such as a Markdown pipe table with its delimiter row
- **THEN** `render_prefix` carries that line and its delimiter, so fragments are valid in
  that form, including for a table the provider marked as having no header — the prefix is
  never empty for such a form

#### Scenario: Rows carried in the prefix are identified

- **WHEN** `render_prefix` carries one or more of the table's rows
- **THEN** the table records which rows those are, so a consumer knows which rows every
  fragment repeats rather than inferring it from the rendering

#### Scenario: A header row that is not carried in the prefix

- **WHEN** a table reports a header row that `render_prefix` does not carry
- **THEN** it is still reported as a header row, and it remains an ordinary body row in
  document order rather than being moved into the prefix

#### Scenario: The fragment for every body row is the whole table

- **WHEN** a table's rendering is contiguous in `extracted_text`
- **THEN** the fragment composed from all of its body rows equals its full rendering
  exactly, byte for byte — which holds for every table, including one whose header rows are
  not its leading rows and one the provider marked as having no header

#### Scenario: Rows carry their own source range

- **WHEN** a body row's rendering occupies a contiguous range of `extracted_text`
- **THEN** the row records that range; and where it does not, the row records no range
  rather than an approximate one

#### Scenario: Rows joined by a merged cell are marked inseparable

- **WHEN** a cell spans several rows
- **THEN** the rows it covers below its first are marked as continuing from that row, so a
  consumer can avoid separating them from the content rendered only in the first

#### Scenario: Cell spans are not row boundaries

- **WHEN** a consumer needs the extent of a rendered row
- **THEN** it uses the row's own rendering or recorded range, because cell spans cover cell
  content only and exclude the markup around it, are absent for empty cells, and may be
  discontiguous within a single cell

#### Scenario: Rendering is not constrained

- **WHEN** an extractor renders tables as HTML and another renders them as pipe tables
- **THEN** both satisfy this specification, and a consumer composing the provided strings
  behaves identically for either

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
- **THEN** every cell's `(row_index, column_index)` extended by its spans tiles the
  declared `row_count` × `column_count` grid without overlap, so the grid is rebuilt exactly

#### Scenario: Paragraph roles preserved

- **WHEN** the service assigns a paragraph a role such as title, section heading, page
  header, page footer, or footnote
- **THEN** that role is present on the corresponding paragraph, expressed canonically

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
