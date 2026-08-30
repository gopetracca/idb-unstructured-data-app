# capability-discovery Specification

## Purpose

Let a client discover, at runtime, what the deployed pipeline can actually do —
which document formats it can extract, which chunking strategies are available with which
parameters, and which embedding models with which dimensions — rather than hard-coding
assumptions that drift from the deployment's configuration.

## Requirements

### Requirement: Pipeline Capabilities Endpoint

The system SHALL report the configured adapters' supported formats, chunking strategies,
and embedding models in one response.

#### Scenario: Capabilities retrieved

- **WHEN** `GET /api/v1/capabilities` is called with `documents.read`
- **THEN** the response is `200` carrying `supported_formats`, `chunking_strategies`, and `embedding_models`

#### Scenario: Values reflect the running configuration

- **WHEN** the response is built
- **THEN** the formats come from the configured document intelligence adapter, the strategies from the configured chunker, and the models from the configured embedding adapter — not from a static list

#### Scenario: Strategy parameters listed

- **WHEN** chunking strategies are reported
- **THEN** each carries the names of the parameters it accepts

#### Scenario: Model dimensions listed

- **WHEN** embedding models are reported
- **THEN** each carries its vector dimension

#### Scenario: Capability lookup failure

- **WHEN** building the response raises
- **THEN** the response is `500` with error `InternalServerError`

### Requirement: Supported Formats Endpoint

The system SHALL expose the extraction adapter's supported content types on their own
endpoint.

#### Scenario: Formats retrieved

- **WHEN** `GET /documents/supported-formats` is called with `documents.read`
- **THEN** the response lists the content types the configured extraction adapter accepts

### Requirement: OpenAPI Documentation

The system SHALL publish an OpenAPI document describing every route, its security
requirements, and its response models.

#### Scenario: Security scheme documented

- **WHEN** the OpenAPI document is generated
- **THEN** bearer authentication is registered as a security scheme and each protected route declares the permission it requires

#### Scenario: Deprecated routes marked

- **WHEN** a route has been superseded
- **THEN** it is marked deprecated in the OpenAPI document rather than removed
