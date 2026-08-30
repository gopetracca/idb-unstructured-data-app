# authentication-authorization Specification

## Purpose

Protect every `/api/v1/*` endpoint with a validated Microsoft Entra ID bearer token and
a resource-oriented permission check. The capability covers token validation (signature,
issuer, audience, expiry), JWKS key retrieval and caching, the four-permission scope
model with its dual delegated/App Role spellings, and the fail-closed startup guard that
refuses to serve traffic when authentication is misconfigured.

## Requirements

### Requirement: Bearer Token Authentication

The system SHALL require a Microsoft Entra ID RS256 bearer token on every `/api/v1/*`
request when `ENTRA_ID_ENABLED` is true, and SHALL reject requests whose token is
missing, malformed, unverifiable, expired, or issued for another issuer or audience.

#### Scenario: Missing bearer token

- **WHEN** a request to a protected endpoint carries no `Authorization: Bearer` header
- **THEN** the system responds `401 Unauthorized` with error `Unauthorized`, message `Missing bearer token`
- **AND** the response carries a `WWW-Authenticate` header naming the required scope

#### Scenario: Valid token

- **WHEN** a request carries a token whose RS256 signature verifies against the tenant JWKS, whose `iss` is `https://login.microsoftonline.com/{tenant_id}/v2.0`, whose `aud` is an accepted audience, and which is within its validity window
- **THEN** the request is authenticated and the claims are used to build the current user

#### Scenario: Expired token

- **WHEN** a token's `exp` is in the past by more than the 30-second leeway
- **THEN** the system responds `401 Unauthorized` with message `Token has expired`

#### Scenario: Wrong audience

- **WHEN** a token's `aud` matches none of the accepted audiences
- **THEN** the system responds `401 Unauthorized` with message `Invalid token audience`

#### Scenario: Wrong issuer

- **WHEN** a token's `iss` is not the configured tenant issuer
- **THEN** the system responds `401 Unauthorized` with message `Invalid token issuer`

#### Scenario: Clock skew tolerance

- **WHEN** a token's `exp` or `nbf` is off by no more than 30 seconds relative to this service's clock
- **THEN** the token is still accepted

### Requirement: Accepted Token Audiences

The system SHALL accept both the bare client ID and the `api://{client_id}` identifier
URI as valid audiences, because Entra emits `aud` differently for v1 and v2 access
tokens, unless an explicit `ENTRA_ID_AUDIENCE` override is configured.

#### Scenario: v2 token carrying the bare client ID

- **WHEN** `ENTRA_ID_AUDIENCE` is unset and a token carries `aud` equal to the configured client ID GUID
- **THEN** the audience check passes

#### Scenario: v1 token carrying the identifier URI

- **WHEN** `ENTRA_ID_AUDIENCE` is unset and a token carries `aud` equal to `api://{client_id}`
- **THEN** the audience check passes

#### Scenario: Explicit audience override

- **WHEN** `ENTRA_ID_AUDIENCE` is set
- **THEN** only that single value is accepted as the audience

### Requirement: Identity Claims Required

The system SHALL require the `oid` and `tid` claims on an otherwise valid token and
SHALL treat their absence as an authentication failure rather than a server error.

#### Scenario: Token signed correctly but missing oid

- **WHEN** a token verifies but carries no `oid` claim
- **THEN** the system responds `401 Unauthorized` naming the missing claims
- **AND** the failure is logged as a warning, not raised as a `500`

### Requirement: Resource-Oriented Permission Model

The system SHALL govern the whole API surface with exactly four permissions —
`Search`, `documents.read`, `documents.write`, and `admin` — and SHALL enforce them by
exact membership with no implication between permissions.

#### Scenario: Verb-to-permission mapping

- **WHEN** a route is declared
- **THEN** GET reads require `documents.read`, POST/PATCH writes require `documents.write`, DELETEs require `admin`, `/search/*` requires `Search`, and `/collections/*` and `/analytics/*` require `admin`

#### Scenario: Admin does not imply read

- **WHEN** a token grants only `admin` and the request targets an endpoint requiring `documents.read`
- **THEN** the system responds `403 Forbidden` with error `Forbidden` and a `details.required` list

#### Scenario: Authorized request

- **WHEN** a token grants the exact permission a route declares
- **THEN** the request proceeds to the handler

### Requirement: Dual Permission Spellings

The system SHALL accept either the delegated-scope spelling or its App Role twin
(suffixed `.All`) for a given permission, because Entra forbids the same literal
appearing in both `appRoles` and `oauth2PermissionScopes` on one application.

#### Scenario: Delegated caller

- **WHEN** a token's `scp` claim contains `documents.read` and the route requires `documents.read`
- **THEN** authorization succeeds

#### Scenario: App-only caller

- **WHEN** a token's `roles` claim contains `documents.read.All` and the route requires `documents.read`
- **THEN** authorization succeeds

#### Scenario: Unrecognized requirement

- **WHEN** a route declares a permission literal outside the four-permission model
- **THEN** only an exact match of that literal satisfies it

### Requirement: Scope Claim Parsing

The system SHALL parse granted permissions as the union of the `roles` array and the
space-delimited `scp` string, splitting `scp` on whitespace so that membership is tested
against whole values rather than substrings.

#### Scenario: Substring escalation is prevented

- **WHEN** a token's `scp` is the single value `documents.readonly` and a route requires `documents.read`
- **THEN** authorization fails with `403 Forbidden`

#### Scenario: Both claims present

- **WHEN** a token carries both `roles` and `scp`
- **THEN** the granted set is the union of the two

#### Scenario: Defensive claim shapes

- **WHEN** `roles` arrives as a space-delimited string or `scp` arrives as an array
- **THEN** the system still derives the correct set of values

### Requirement: Calling Application Allowlist

The system SHALL optionally restrict which calling applications may present a valid
token, matching the token's `azp` or `appid` claim against
`ENTRA_ID_ALLOWED_CLIENT_IDS`.

#### Scenario: Allowlist configured and caller not listed

- **WHEN** `ENTRA_ID_ALLOWED_CLIENT_IDS` is non-empty and the token's `azp`/`appid` is not in it
- **THEN** the system responds `401 Unauthorized` with message `Calling application is not allowed`

#### Scenario: Allowlist empty

- **WHEN** `ENTRA_ID_ALLOWED_CLIENT_IDS` is empty
- **THEN** any caller holding a token for an accepted audience is allowed

### Requirement: JWKS Caching And Rotation

The system SHALL cache Entra signing keys by `kid` with a configurable TTL, refresh on
expiry, force a refresh when an unknown `kid` arrives so key rotation is handled between
TTL cycles, and serialize concurrent refreshes behind a lock.

#### Scenario: First request on a freshly started process

- **WHEN** no JWKS fetch has yet occurred
- **THEN** the cache is treated as stale and a fetch is performed, regardless of the host's monotonic-clock origin

#### Scenario: Key rotation mid-TTL

- **WHEN** a token presents a `kid` absent from the cache and no forced refresh happened within `ENTRA_ID_JWKS_FORCE_REFRESH_MIN_INTERVAL_SECONDS`
- **THEN** the system refetches the JWKS once and retries the lookup

#### Scenario: Unknown-kid flood is throttled

- **WHEN** many requests arrive carrying bogus `kid` values within the force-refresh interval
- **THEN** at most one outbound JWKS fetch is issued in that interval and the remaining requests fail with `401`

#### Scenario: Concurrent refresh

- **WHEN** several requests trigger a refresh simultaneously
- **THEN** one fetch is performed and the others reuse its result

### Requirement: Fail-Closed Authentication Startup Guard

The system SHALL refuse to start when authentication is unsafe or unusable as
configured, converting a silent exposure into an immediate deployment failure.

#### Scenario: Auth disabled in a deployed environment

- **WHEN** `ENTRA_ID_ENABLED` is false, the environment is not a development environment, and `ALLOW_ANONYMOUS_AUTH` is false
- **THEN** startup aborts with an `AuthConfigurationError` naming the environment

#### Scenario: Auth enabled but incompletely configured

- **WHEN** `ENTRA_ID_ENABLED` is true but `ENTRA_ID_TENANT_ID` or `ENTRA_ID_CLIENT_ID` is missing
- **THEN** startup aborts with an `AuthConfigurationError`, because every request would otherwise 401

#### Scenario: Development environment

- **WHEN** `ENTRA_ID_ENABLED` is false and the environment is `development`, `dev`, or `local`
- **THEN** startup proceeds and logs a warning that all requests are accepted anonymously

#### Scenario: Explicit anonymous escape hatch

- **WHEN** `ENTRA_ID_ENABLED` is false and `ALLOW_ANONYMOUS_AUTH` is true
- **THEN** startup proceeds with a warning, for running a non-development build locally

### Requirement: Anonymous Development User

When authentication is disabled the system SHALL resolve every request to a synthetic
anonymous user holding all four permissions, so route handler signatures are identical
across environments.

#### Scenario: Request with auth disabled

- **WHEN** `ENTRA_ID_ENABLED` is false and any protected endpoint is called
- **THEN** the request resolves to user `anonymous` with all four permissions granted and no token is required

### Requirement: Route Security Contract

The system SHALL require authentication on every mounted operation except an explicit
allowlist of unauthenticated probes, and SHALL declare exactly one permission per
operation according to the four-permission model. Both invariants are enforced by guard
tests against the generated OpenAPI document and the mounted route table, so a new route
cannot ship unprotected or with drifted authorization.

#### Scenario: Unauthenticated allowlist

- **WHEN** the mounted operations are enumerated
- **THEN** only `GET /`, `GET /health/live`, and `GET /health/ready` are reachable without authentication

#### Scenario: New route without a security requirement

- **WHEN** an operation outside the allowlist declares no security requirement
- **THEN** the guard test fails naming the offending method and path

#### Scenario: Stale allowlist entry

- **WHEN** an allowlisted path is no longer mounted
- **THEN** the guard test fails, so the allowlist cannot outlive the route it excused

#### Scenario: Scope drift

- **WHEN** an operation's declared permission differs from the expected mapping
- **THEN** the guard test fails, so adding, removing, or re-scoping a route is a deliberate change to the mapping

### Requirement: Startup Guard Arming Depends On ENVIRONMENT

The system SHALL derive whether the fail-closed authentication guard fires from the
`ENVIRONMENT` setting, which defaults to a development value — so the guard is inert
unless the environment is set explicitly per deployment.

#### Scenario: ENVIRONMENT unset

- **WHEN** `ENVIRONMENT` is not configured
- **THEN** it defaults to `dev`, the environment is treated as development, and the guard does not fire even with `ENTRA_ID_ENABLED` false

#### Scenario: ENVIRONMENT set to a deployed value

- **WHEN** `ENVIRONMENT` is set to a non-development value such as `test` or `prod`
- **THEN** the guard is armed and refuses to start with authentication disabled
