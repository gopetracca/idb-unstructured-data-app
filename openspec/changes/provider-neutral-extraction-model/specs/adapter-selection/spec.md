# adapter-selection Delta

## ADDED Requirements

### Requirement: Extraction Adapters Are Interchangeable

The extraction port SHALL be defined in provider-neutral terms, so that adding an
extraction service is an adapter and not a change to any consumer.

#### Scenario: The port names no provider

- **WHEN** the extraction port is read
- **THEN** its types and its vocabulary are canonical, and no application or presentation
  code refers to a specific extraction service

#### Scenario: A second extractor changes no consumer

- **WHEN** an extraction adapter for a different service is added and selected
- **THEN** the chunking, vectorization, ingestion, and search stages require no change,
  because they consume only the canonical output

#### Scenario: The fake adapter satisfies the same contract

- **WHEN** `DOCUMENT_INTELLIGENCE_USE_FAKE` is true
- **THEN** the fake adapter emits the canonical output — blocks, canonical cell roles,
  header rows, and rendered table text — so that local runs exercise the contract rather
  than a simplification of it
