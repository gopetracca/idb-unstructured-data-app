# blob-artifact-storage Specification

## Purpose

Hold every byte the pipeline produces, laid out so a document's artifacts are locatable
and removable as a unit. One container per pipeline stage, one tenant- and file-scoped
prefix per document, and JSON artifacts whose shape each downstream stage depends on.
SQL holds the authoritative pointer to each artifact; this capability defines what the
pointer points at.

## Requirements

### Requirement: Container Per Pipeline Stage

The system SHALL separate artifacts by pipeline stage into distinct containers, each
independently configurable.

#### Scenario: Containers

- **WHEN** the pipeline runs
- **THEN** original files land in the raw container, extracted text in the text container, chunks in the chunks container, and embeddings in the embeddings container

#### Scenario: Container names are configurable

- **WHEN** a container name setting is supplied
- **THEN** that name is used, defaulting to `raw`, `text`, `chunks`, and `embeddings`

### Requirement: Tenant And File Scoped Paths

The system SHALL prefix every artifact path with the tenant and file identifier, so one
document's artifacts form a single removable subtree.

#### Scenario: Path shapes

- **WHEN** artifacts are written
- **THEN** the raw file goes to `{tenant_id}/{file_id}/{filename}`, the extraction stage's text output and raw analysis under `{tenant_id}/{file_id}/text/` and `{tenant_id}/{file_id}/analysis/` at a path unique to the run that produced them, each chunk to `{tenant_id}/{file_id}/chunks/{chunk_id}.json`, and each embedding under `{tenant_id}/{file_id}/embeddings/`

#### Scenario: Run-scoped artifacts are located by reference, not by name

- **WHEN** a consumer needs the extraction stage's text output or raw analysis
- **THEN** it follows `text_blob_ref` or `analysis_blob_ref` on the document, because the filename is unique to a run and cannot be derived from the tenant and file identifier alone

#### Scenario: Deleting a document's artifacts

- **WHEN** a document is deleted
- **THEN** every container is swept by the `{tenant_id}/{file_id}/` prefix rather than by enumerating known filenames

#### Scenario: Listing a document's artifacts

- **WHEN** a stage needs a document's artifacts
- **THEN** it lists by prefix, so artifacts added by a later run are picked up without a manifest

### Requirement: Artifact Write Semantics

The system SHALL overwrite artifacts by default and record their content type, so a
re-run of a stage replaces its output rather than failing or duplicating — except where a
stage writes run-scoped outputs, which are never overwritten and are instead superseded by
moving the reference that locates them. Every artifact deletion in the system is
best-effort, including the sweep performed when a document is deleted: correctness rests on
the reference and on the SQL record, never on a blob having been removed. No component
retries a failed deletion or reconciles what was left behind.

#### Scenario: Re-running a stage

- **WHEN** a stage writes an artifact whose path already exists
- **THEN** the existing blob is overwritten

#### Scenario: Re-running the extraction stage

- **WHEN** the extraction stage runs again for a document that already has stored outputs
- **THEN** it writes to paths unique to the new run, so nothing previously published is overwritten and the document reads as the last completed run left it until the new references are published

#### Scenario: Superseded run-scoped artifacts are cleaned up

- **WHEN** new references are published for a document
- **THEN** deletion of the artifacts the references previously pointed at is attempted, so unreferenced outputs do not ordinarily accumulate

#### Scenario: Cleanup of a superseded artifact fails

- **WHEN** deleting a displaced or abandoned artifact raises
- **THEN** the failure is logged as a warning and the stage's outcome is unchanged, because the blob is already unreachable — the reference, not the path, is what locates content — so the cost is leaked storage rather than exposure or an inconsistent read

#### Scenario: Document deletion is where leaked artifacts are ordinarily reclaimed

- **WHEN** a document is deleted after one or more cleanup attempts failed
- **THEN** the prefix sweep removes the leaked artifacts along with the rest of the document's subtree, because it sweeps by prefix rather than by enumerating names it would have no way to know

#### Scenario: The final sweep is best-effort too

- **WHEN** the prefix sweep fails while a document is being deleted
- **THEN** the failure is logged, the authoritative SQL deletion still proceeds, and the artifacts remain — and because the record that named them is now gone, nothing in the system reports them and reclaiming them needs reconciliation outside these capabilities

#### Scenario: No component reconciles leaked artifacts

- **WHEN** any cleanup attempt has failed
- **THEN** no retry, sweep, or reconciliation runs later on its own, so the leak persists until something outside these capabilities removes it

#### Scenario: Content type recorded

- **WHEN** a JSON artifact is written
- **THEN** it is stored as `application/json; charset=utf-8`, and text payloads are encoded as UTF-8 before upload

#### Scenario: Raw upload metadata

- **WHEN** an uploaded file is stored
- **THEN** the blob carries its declared content type and blob metadata naming the file and tenant

### Requirement: Artifact Formats

The system SHALL write each stage's output in the JSON shape the next stage reads, and
SHALL ignore blobs that do not match.

#### Scenario: Extracted text artifact

- **WHEN** extraction writes its output
- **THEN** the JSON carries the extracted text plus extraction metadata such as page count, and the chunking stage reads the extracted text from it

#### Scenario: Chunk artifact

- **WHEN** a chunk is written
- **THEN** the JSON carries the chunk's content and positional fields, while its searchable metadata is held in SQL rather than duplicated into the blob

#### Scenario: Embedding artifact

- **WHEN** an embedding is written
- **THEN** the JSON carries the file and chunk identifiers, the vector, the chunk text, and the embedding metadata needed for indexing

#### Scenario: Non-JSON blobs skipped

- **WHEN** the ingest stage lists a document's embeddings prefix
- **THEN** blobs whose names do not end in `.json` are skipped

#### Scenario: Unreadable artifact does not fail the batch

- **WHEN** one embedding artifact cannot be downloaded or parsed
- **THEN** the failure is logged and the remaining artifacts are still loaded
