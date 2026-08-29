# health-and-readiness Specification

## Purpose

Give the hosting platform two distinct, unauthenticated signals: whether the process is
alive, and whether it can currently serve traffic. Separating them prevents a slow or
failing downstream from triggering replica restarts, while still draining a replica whose
dependencies are unreachable.

## Requirements

### Requirement: Liveness Probe

The system SHALL expose a liveness endpoint that performs no dependency I/O, so a
downstream outage can never cause the platform to restart a healthy replica.

#### Scenario: Process is up

- **WHEN** `GET /health/live` is called
- **THEN** the response is `200` carrying `status` `alive` and the service name, without touching SQL Server or Azure AI Search

#### Scenario: Legacy root endpoint

- **WHEN** `GET /` is called
- **THEN** it behaves as a liveness check returning `status` `ok` and the service name, retained for backwards compatibility

### Requirement: Readiness Probe

The system SHALL expose a readiness endpoint that verifies the dependencies needed to
serve traffic and reports a per-dependency status map.

#### Scenario: All dependencies reachable

- **WHEN** `GET /health/ready` is called and both SQL Server and Azure AI Search respond
- **THEN** the response is `200` carrying `status` `ready` and a `checks` map of `ok` values

#### Scenario: A dependency is unreachable

- **WHEN** any check fails
- **THEN** the response is `503` carrying `status` `not_ready` and a `checks` map naming the failing dependency and its error type

#### Scenario: Checks run concurrently with a bounded timeout

- **WHEN** the readiness checks run
- **THEN** they execute concurrently and each is bounded at 4 seconds, below the platform's 5-second probe timeout

#### Scenario: A check times out

- **WHEN** a dependency does not answer within the timeout
- **THEN** that check reports `timeout`, the overall result is not ready, and a warning is logged

#### Scenario: SQL Server disabled

- **WHEN** SQL Server is not configured
- **THEN** the SQL check reports `disabled` and does not fail readiness

#### Scenario: Startup probe reuse

- **WHEN** the platform runs its startup probe
- **THEN** the same readiness endpoint serves it

### Requirement: Probes Are Unauthenticated

The system SHALL leave both probe endpoints unauthenticated, because platform probes
cannot present bearer tokens, and SHALL expose nothing beyond dependency reachability.

#### Scenario: Probe without a token

- **WHEN** either probe is called with no `Authorization` header
- **THEN** it responds normally

#### Scenario: No data disclosure

- **WHEN** a readiness check fails
- **THEN** the response names the dependency and the exception type only, never connection strings, credentials, or query detail
