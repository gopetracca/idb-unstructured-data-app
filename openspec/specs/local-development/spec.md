# local-development Specification

## Purpose

Let a developer run the whole pipeline on a laptop with no Azure subscription: emulated
storage, a local SQL Server, and deterministic fakes standing in for the paid AI
services. Tests that would call a real cloud service are opt-in, so the default test run
is fast, free, and offline.

## Requirements

### Requirement: Local Dependency Stack

The system SHALL provide a container-composed local environment supplying every
infrastructure dependency the application needs.

#### Scenario: Emulated storage

- **WHEN** the local stack starts
- **THEN** a storage emulator provides blob, queue, and table endpoints, and the application's default connection string points at it

#### Scenario: Local database

- **WHEN** the local stack starts
- **THEN** a SQL Server container is started with a health check, a database is created, and migrations are applied before the app is expected to serve

#### Scenario: Application port

- **WHEN** the local application container runs
- **THEN** the Functions host is reachable on the documented local port

#### Scenario: Corporate CA off by default

- **WHEN** the local image is built through the compose file
- **THEN** the corporate CA build arguments default to disabled with an empty placeholder certificate

### Requirement: Deterministic Fakes For Paid Services

The system SHALL allow document intelligence, chunking, and embeddings to be replaced by
deterministic fakes, so the full pipeline runs without an Azure account.

#### Scenario: Running the pipeline offline

- **WHEN** the fake flags are enabled
- **THEN** upload, extraction, chunking, vectorization, and ingestion all complete against emulated storage and the local database

#### Scenario: Fakes are honest about being fakes

- **WHEN** a fake adapter is selected
- **THEN** it is chosen explicitly by setting, or implicitly by the unconfigured-dependency fallback that logs a warning

### Requirement: Opt-In Integration Tests

The system SHALL keep tests that call real external services off by default, enabled per
service by an explicit setting.

#### Scenario: Default test run

- **WHEN** the test suite runs with no extra configuration
- **THEN** no test calls Azure Document Intelligence, Azure OpenAI, or Azure AI Search

#### Scenario: Enabling a service's integration tests

- **WHEN** the corresponding run-tests setting is set to a truthy value such as `on`, `1`, `true`, or `yes`
- **THEN** that service's integration tests are enabled

#### Scenario: Unrecognised value

- **WHEN** a run-tests setting holds a value that is neither truthy nor falsy
- **THEN** it is treated as disabled, so a typo cannot accidentally bill a real service

### Requirement: Test Categorisation

The system SHALL categorise tests by marker so a developer can select a subset, and
SHALL reject unknown markers.

#### Scenario: Markers

- **WHEN** a test is written
- **THEN** it may be marked `unit`, `integration`, `api`, `slow`, or with a `requires_*` marker naming the dependency it needs

#### Scenario: Unknown marker

- **WHEN** a test declares a marker that is not registered
- **THEN** the run fails rather than silently ignoring the marker

#### Scenario: Coverage reporting

- **WHEN** the suite runs
- **THEN** coverage over the source tree is measured and reported to the terminal and to an HTML directory

### Requirement: Tests Mirror The Source Layout

The system SHALL organise tests to mirror the layered source tree, so the layer a test
belongs to is evident from its path.

#### Scenario: Unit tests

- **WHEN** a unit test is added
- **THEN** it lives under the path mirroring its module's layer, such as core, application, infrastructure, or presentation

#### Scenario: Integration tests

- **WHEN** an integration test is added
- **THEN** it lives under the integration tree, separated into HTTP-level and infrastructure-level suites

### Requirement: Developer Token Helpers

The system SHALL provide scripts for minting a bearer token against the real app
registration, covering both permission models, so a developer can exercise the
authenticated API without embedding credentials in tooling.

#### Scenario: App-only token

- **WHEN** the client-credentials helper runs with a client secret supplied through the environment
- **THEN** it returns an app-only token carrying the `roles` claim for whatever App Roles the service principal is assigned

#### Scenario: Delegated token

- **WHEN** a token carrying delegated `scp` scopes is needed
- **THEN** the interactive authorization-code helper is used, because client credentials can never produce `scp`

#### Scenario: Inspecting claims

- **WHEN** a helper is run in decode mode
- **THEN** it prints the token's claims instead of the raw token

#### Scenario: Secrets come from the environment

- **WHEN** a helper needs a client secret
- **THEN** it is read from an environment variable sourced from the key vault, never hard-coded
