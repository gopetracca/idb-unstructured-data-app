# tenant-resolution Specification

## Purpose

Decide the effective tenant for every request in one place, so no caller can reach
another tenant's data by supplying a tenant value at the API boundary. The system is
currently in a single-tenant phase: the effective tenant is a configured constant, while
the multi-tenant plumbing in use cases, repositories, and storage paths is preserved for
a later per-user rollout.

## Requirements

### Requirement: Server-Side Tenant Resolution

The system SHALL derive the effective tenant identifier server-side for every request
and SHALL NOT accept a tenant value from the client.

#### Scenario: Client supplies a tenant header

- **WHEN** a request carries an `X-Tenant-Id` header, a `tenant_id` query parameter, or a `tenant_id` body field
- **THEN** the value is ignored and the effective tenant remains the server-resolved one

#### Scenario: Single-tenant phase

- **WHEN** any request is handled
- **THEN** the effective tenant is the configured `DEFAULT_TENANT_ID` (default `default`)

#### Scenario: Single resolution point

- **WHEN** the tenant model changes to per-user
- **THEN** only the resolver changes to read `CurrentUser.tenant_id` (the `tid` claim), and no route signature changes

### Requirement: Tenant-Scoped Storage Layout

The system SHALL prefix every blob path and scope every metadata query with the
effective tenant identifier, so tenant data remains separable end to end.

#### Scenario: Blob paths

- **WHEN** a document artifact is written to blob storage
- **THEN** its path begins `{tenant_id}/{file_id}/`

#### Scenario: Metadata reads

- **WHEN** a document is fetched, listed, updated, or deleted
- **THEN** the query is scoped by the effective tenant, and a document belonging to another tenant is reported as not found

### Requirement: No Client-Supplied Tenant In The API Contract

The system SHALL keep the tenant out of the public request contract entirely, enforced
by guard tests over the generated OpenAPI document rather than by convention.

#### Scenario: No tenant parameter

- **WHEN** the mounted operations are enumerated
- **THEN** no operation declares a header or query parameter whose name contains `tenant`

#### Scenario: No tenant in request bodies

- **WHEN** the request-body schemas are enumerated
- **THEN** none exposes a `tenant_id` property

#### Scenario: Responses may still carry the tenant

- **WHEN** a response schema is inspected
- **THEN** it may include `tenant_id`, because the invariant concerns untrusted input, not output
