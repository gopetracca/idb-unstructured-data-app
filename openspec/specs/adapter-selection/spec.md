# adapter-selection Specification

## Purpose

Choose, at composition time, which implementation backs each port — a real service
adapter, a deterministic fake, or (for chunking) one of two real libraries — from
settings alone, so no application or domain code knows which is in play. This is also
where the system's riskiest configuration behaviour lives: an unconfigured Azure
dependency silently falls back to a fake.

## Requirements

### Requirement: Ports Are Resolved From Settings

The system SHALL wire every port to an implementation in a single composition root, and
application and domain code SHALL depend only on the port.

#### Scenario: Composition root

- **WHEN** the application or the function app starts
- **THEN** one container resolves the adapters, repositories, and use cases, and wires them into the HTTP routes and queue triggers

#### Scenario: Single instances

- **WHEN** a port is resolved more than once
- **THEN** the same instance is returned, so clients, connection pools, and caches are shared rather than rebuilt per request

### Requirement: Explicit Fake Adapters

The system SHALL provide a deterministic fake for document intelligence, chunking, and
embeddings, selectable per adapter, so the pipeline can run with no Azure dependency.

#### Scenario: Fake requested

- **WHEN** `DOCUMENT_INTELLIGENCE_USE_FAKE`, `CHUNKING_USE_FAKE`, or `EMBEDDING_USE_FAKE` is true
- **THEN** the corresponding fake adapter is used regardless of whether the real one is configured

#### Scenario: Simulated latency

- **WHEN** the fake document intelligence adapter runs
- **THEN** it applies the configured simulated delay, so timing-sensitive behaviour is still exercised

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

### Requirement: Silent Fallback To Fakes When Azure Is Unconfigured

The system SHALL fall back to a fake adapter when a real Azure dependency is not
configured, logging a warning and continuing to start rather than failing. This is a
deliberate development affordance with a production hazard: a deploy missing an endpoint
serves plausible but fabricated results instead of failing.

#### Scenario: Document intelligence unconfigured

- **WHEN** `DOCUMENT_INTELLIGENCE_ENDPOINT` is empty and the fake is not explicitly requested
- **THEN** a warning naming the missing settings is logged and the fake adapter is used, so extraction returns synthetic text

#### Scenario: Embeddings unconfigured

- **WHEN** `EMBEDDING_ENDPOINT` or `EMBEDDING_DEPLOYMENT_NAME` is empty and the fake is not explicitly requested
- **THEN** a warning naming the missing settings is logged and the fake adapter is used, so documents are indexed with fabricated vectors and search returns meaningless rankings

#### Scenario: The warning is the only signal

- **WHEN** a fallback occurs
- **THEN** startup succeeds, the readiness probe still reports ready, and no endpoint reports that a fake is in use — the startup warning is the sole indication

### Requirement: Chunker Adapter Selection

The system SHALL select between two real chunking libraries by setting, defaulting to
the structure-aware one.

#### Scenario: Default adapter

- **WHEN** `CHUNKING_ADAPTER` is unset
- **THEN** the Chonkie structure-aware chunker is used

#### Scenario: LlamaIndex adapter

- **WHEN** `CHUNKING_ADAPTER` is any value other than `chonkie`
- **THEN** the LlamaIndex chunker is used

#### Scenario: Supported strategies follow the adapter

- **WHEN** the capabilities endpoint reports chunking strategies
- **THEN** it reports the strategies of whichever adapter is active, not a fixed list

### Requirement: The Metadata Store Has No Fallback

The system SHALL treat SQL Server as a hard requirement for the document repositories
and SHALL fail loudly rather than substituting an alternative.

#### Scenario: SQL Server disabled

- **WHEN** a document, chunk index, or processing events repository is resolved while `SQL_SERVER_ENABLED` is false or no session factory exists
- **THEN** a runtime error naming `SQL_SERVER_ENABLED` and `SQL_SERVER_DATABASE_URL` is raised

#### Scenario: Contrast with the adapter fallbacks

- **WHEN** comparing this behaviour with document intelligence and embeddings
- **THEN** the metadata store deliberately does not degrade, because a missing document record is unrecoverable while a fabricated embedding merely looks wrong

### Requirement: Resource Lifecycle

The system SHALL release adapter resources on shutdown, in reverse dependency order.

#### Scenario: Application shutdown

- **WHEN** the FastAPI lifespan ends
- **THEN** container resources with a close method are shut down

#### Scenario: Function host shutdown

- **WHEN** the function app process exits
- **THEN** the same shutdown runs via an exit hook, so queue-trigger execution paths release clients too
