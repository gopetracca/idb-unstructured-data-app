# metadata-persistence Delta

## ADDED Requirements

### Requirement: Analysis Blob Reference Recorded

The document record SHALL carry a nullable reference to the stored raw analysis result, so
the full extraction output is locatable without reconstructing a path by convention.

#### Scenario: Column present and nullable

- **WHEN** the schema is migrated
- **THEN** the document table has a nullable `analysis_blob_ref` column sized for a blob
  path, and existing rows keep the value null

#### Scenario: Reference written after extraction

- **WHEN** the raw analysis is stored during the `convert` stage
- **THEN** `analysis_blob_ref` is updated to that blob path before the stage reports success

#### Scenario: Reference absent

- **WHEN** the raw analysis was not stored, whether by configuration or write failure
- **THEN** `analysis_blob_ref` stays null and no downstream reader treats that as an error
