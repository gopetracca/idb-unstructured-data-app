# pipeline-analytics Specification

## Purpose

Make pipeline behaviour observable to operators: a per-document timeline of stage
transitions and aggregate duration statistics per stage, both derived from the processing
events each stage records. Analytics depend on SQL Server and degrade explicitly when it
is disabled.

## Requirements

### Requirement: Processing Event Recording

The system SHALL record a processing event for each stage execution, carrying the stage,
its outcome, a timestamp, the duration, and any error message.

#### Scenario: Event fields

- **WHEN** a stage finishes
- **THEN** an event is recorded with `file_id`, `tenant_id`, `stage`, `status`, `event_timestamp`, `duration_ms`, and `error_message` when applicable

#### Scenario: Event statuses

- **WHEN** a stage outcome is recorded
- **THEN** the status is one of `success`, `failed`, or `retrying`

#### Scenario: Event logging never breaks a stage

- **WHEN** writing a processing event fails
- **THEN** the failure is logged as a warning and the stage's own outcome is unchanged

### Requirement: Document Processing Timeline

The system SHALL return a document's ordered stage transitions with a total elapsed
duration.

#### Scenario: Timeline retrieved

- **WHEN** `GET /api/v1/documents/{file_id}/processing-timeline` is called with `admin`
- **THEN** the response is `200` carrying the ordered events, each with `event_id`, `stage`, `status`, `event_timestamp`, `duration_ms`, and `error_message`

#### Scenario: Total duration

- **WHEN** the timeline holds at least two events
- **THEN** `total_duration_ms` is the elapsed time between the first and last event

#### Scenario: Fewer than two events

- **WHEN** the timeline holds zero or one event
- **THEN** `total_duration_ms` is null

### Requirement: Stage Duration Statistics

The system SHALL return aggregate processing duration statistics per stage for a tenant,
optionally narrowed to one stage.

#### Scenario: Statistics retrieved

- **WHEN** `GET /api/v1/analytics/stage-durations` is called with `admin`
- **THEN** the response is `200` carrying, per stage, the average, minimum, and maximum duration in milliseconds and the sample count

#### Scenario: Stage filter

- **WHEN** the `stage` query parameter is supplied
- **THEN** only that stage's statistics are returned

### Requirement: Analytics Requires The Metadata Store

The system SHALL report analytics as unavailable rather than empty when SQL Server is
disabled.

#### Scenario: SQL Server disabled

- **WHEN** either analytics endpoint is called and the processing events repository is not configured
- **THEN** the response is `503` with error `FeatureDisabled` and a message naming the SQL Server requirement

### Requirement: Analytics Requires Admin

The system SHALL restrict both analytics endpoints to the `admin` permission.

#### Scenario: Non-admin caller

- **WHEN** a caller without `admin` requests a timeline or stage statistics
- **THEN** the response is `403 Forbidden`
