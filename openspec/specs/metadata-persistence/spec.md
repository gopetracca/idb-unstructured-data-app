# metadata-persistence Specification

## Purpose

Hold the authoritative record of every document: its identity and storage references, its
processing state, its typed metadata, and its chunk index. SQL Server is the source of
truth for where content lives (blob references) and for everything queried outside the
vector index. Schema evolution runs through Alembic as a gated pre-deploy step.

## Requirements

### Requirement: Relational Document Model

The system SHALL model a document across dedicated tables for identity, pipeline state,
typed metadata, chunk index, chunk metadata, vector references, and processing events.

#### Scenario: Tables

- **WHEN** the schema is provisioned
- **THEN** it contains `files`, `pipeline_state`, `file_metadata`, `chunks`, `chunk_metadata`, `chunk_vector_refs`, and `processing_events`

#### Scenario: Composite document view

- **WHEN** a document is read
- **THEN** its identity, pipeline state, and metadata are assembled into one composite result

#### Scenario: Cascading delete

- **WHEN** a document's `files` row is deleted
- **THEN** its pipeline state, metadata, chunks, and processing events are deleted with it

### Requirement: Blob References Are The Source Of Truth

The system SHALL record, in SQL, the blob path for a document's raw file, its extracted
text, and each of its chunks, and downstream stages SHALL read those references rather
than reconstructing paths by convention.

#### Scenario: Raw reference recorded at upload

- **WHEN** a document is uploaded
- **THEN** `raw_blob_ref` records the raw blob path

#### Scenario: Text reference recorded at extraction

- **WHEN** extraction completes
- **THEN** `text_blob_ref` records the text blob path

#### Scenario: Chunk references recorded at chunking

- **WHEN** chunks are stored
- **THEN** each chunk index row records its `chunk_blob_ref`

#### Scenario: Reference missing

- **WHEN** a stage needs a reference the document does not carry
- **THEN** the stage fails with an explicit reason naming the missing reference rather than guessing a path

### Requirement: Promoted Metadata As Typed Columns

The system SHALL store document metadata as dedicated nullable columns using a
single-table-inheritance layout keyed by `document_category`, rather than as an opaque
JSON blob.

#### Scenario: Category-specific columns

- **WHEN** an operational or publication document is stored
- **THEN** both the shared base columns and that category's specific columns are populated on `file_metadata`

#### Scenario: Non-promoted keys discarded

- **WHEN** supplied metadata carries keys outside the category's promoted field set
- **THEN** they are not persisted

### Requirement: Chunk Index Queries

The system SHALL let the pipeline query a document's chunks by embedding status and
count them, so vectorization is resumable and progress is reportable.

#### Scenario: Pending chunks

- **WHEN** vectorization starts
- **THEN** only chunk rows not yet marked embedded are returned

#### Scenario: Status transitions

- **WHEN** a chunk is embedded or fails
- **THEN** its row is marked embedded with its vector reference, or marked failed

#### Scenario: Counts

- **WHEN** the pipeline reports progress
- **THEN** the total chunk count and the embedded chunk count for a file are available

### Requirement: SQL Server Feature Flag

The system SHALL treat SQL Server as a flagged dependency, so features that require it
report unavailability explicitly rather than failing obscurely.

#### Scenario: Disabled

- **WHEN** `SQL_SERVER_ENABLED` is false
- **THEN** the readiness probe reports the SQL check as `disabled` and analytics endpoints return `503 FeatureDisabled`

#### Scenario: Connection pooling

- **WHEN** SQL Server is enabled
- **THEN** the async engine uses the configured pool size, overflow, and timeout

### Requirement: Alembic Migrations As A Gated Pre-Deploy Step

The system SHALL run schema migrations as a separate pre-deploy job that must succeed
before the new application revision rolls out.

#### Scenario: Migration entrypoint

- **WHEN** `python -m src.infrastructure.sqlserver.run_migrations` runs
- **THEN** Alembic upgrades the database to head using `SQL_SERVER_DATABASE_URL_MIGRATIONS`, falling back to `SQL_SERVER_DATABASE_URL`

#### Scenario: Concurrent migrators serialize

- **WHEN** two migration runs overlap
- **THEN** a session-scoped SQL Server application lock serializes them, waiting up to two minutes before failing with an explicit message

#### Scenario: SQL Server disabled

- **WHEN** `SQL_SERVER_ENABLED` is false
- **THEN** the migration runner logs that it is skipping and exits successfully

#### Scenario: No database URL configured

- **WHEN** neither migration URL is set while SQL Server is enabled
- **THEN** the runner fails with an explicit configuration error

#### Scenario: Migration runner ships in the image

- **WHEN** the container image is built
- **THEN** the migration entrypoint lives under `src/` so it is present in the image, unlike the excluded `scripts/` directory
