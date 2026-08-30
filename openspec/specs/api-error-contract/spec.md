# api-error-contract Specification

## Purpose

Give every API consumer one predictable error shape and a stable mapping from domain
errors to HTTP status codes, so integrators can branch on the `error` type rather than
parse messages. Request-size rejection lives in `edge-protection`; correlation
identifiers live in `observability`.

## Requirements

### Requirement: Uniform Error Response Shape

The system SHALL return errors as a JSON object carrying an `error` type string, a
human-readable `message`, and an optional `details` object.

#### Scenario: Any handled error

- **WHEN** a request fails with a handled domain or auth error
- **THEN** the response body is `{"error": "<Type>", "message": "<text>", "details": <object|null>}`

### Requirement: Domain Error To Status Mapping

The system SHALL map domain errors to HTTP status codes consistently across every
endpoint.

#### Scenario: Duplicate document

- **WHEN** an upload reuses an `ezshare_id` that already exists for the tenant
- **THEN** the response is `409` with error `DuplicateDocument` and `details` naming `ezshare_id` and `existing_file_id`

#### Scenario: Document not found

- **WHEN** a request targets a `file_id` that does not exist for the tenant
- **THEN** the response is `404` with error `DocumentNotFound` and `details` naming `file_id` and `tenant_id`

#### Scenario: Invalid file type

- **WHEN** an upload carries a MIME type outside the allowed list
- **THEN** the response is `400` with error `InvalidFileType` and `details` naming `provided_type` and `allowed_types`

#### Scenario: File too large

- **WHEN** an uploaded file exceeds the configured maximum size
- **THEN** the response is `413` with error `FileSizeExceeded` and `details` naming `size_bytes` and `max_size_bytes`

#### Scenario: Metadata validation failure

- **WHEN** metadata fails field-level validation
- **THEN** the response is `422` with error `MetadataValidationError` and `details` naming `field` and `reason`

#### Scenario: Storage failure

- **WHEN** a blob or metadata storage operation fails
- **THEN** the response is `500` with error `StorageError`, a generic message, and `details` naming only the `operation` — never the underlying exception text

#### Scenario: Unclassified domain error

- **WHEN** a `DomainError` with no specific handler reaches the boundary
- **THEN** the response is `400` with error `DomainError`

#### Scenario: Authentication failure

- **WHEN** a token is missing or invalid
- **THEN** the response is `401` with error `Unauthorized` and a `WWW-Authenticate` header

#### Scenario: Authorization failure

- **WHEN** a valid token lacks a required permission
- **THEN** the response is `403` with error `Forbidden` and `details.required` listing the needed permissions

#### Scenario: Request schema validation failure

- **WHEN** a Pydantic validation error is raised while resolving dependencies
- **THEN** the response is `422` with error `ValidationError` and `details` carrying the field-level error list
