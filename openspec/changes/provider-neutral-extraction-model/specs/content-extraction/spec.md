# content-extraction Delta

## ADDED Requirements

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

- **WHEN** a consumer needs a table's text or its header's text
- **THEN** both are available as strings the extractor produced, in the same form they take
  in `extracted_text`, so that no consumer parses the rendering to recover them

#### Scenario: Rendering is not constrained

- **WHEN** an extractor renders tables as HTML and another renders them as pipe tables
- **THEN** both satisfy this specification, and a consumer reading the provided strings
  behaves identically for either

## MODIFIED Requirements

### Requirement: Structural Layout Elements In Text Output

The extracted-text output SHALL carry the document's structural elements alongside the
markdown — tables, figures, paragraphs with their roles, sections, styles, key-value
pairs, and per-page lines, words, and selection marks — and SHALL carry the canonical
block list described above.

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

#### Scenario: Output written before the block list existed

- **WHEN** a `text.json` written before this change is read
- **THEN** it deserialises with an empty block list, and consumers treat that as structure
  being unavailable rather than as a document with no structure
