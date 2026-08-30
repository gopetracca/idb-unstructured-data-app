# edge-protection Specification

## Purpose

Shape and bound incoming requests before they reach application code, and record which
edge controls this service performs versus which it delegates to the platform edge. The
delegation is deliberate: throttling and origin policy cannot be enforced coherently by
a single replica, so they belong in front of the app — but that means they are absent
here, and the specs say so rather than leaving it to be assumed.

## Requirements

### Requirement: Request Body Size Limiting

The system SHALL reject oversized request bodies before buffering them, using both the
declared `Content-Length` and a streaming byte counter, so peak memory stays bounded on
a memory-capped host.

#### Scenario: Oversized declared Content-Length

- **WHEN** a request declares a `Content-Length` above the file-size limit plus multipart overhead
- **THEN** the system responds `413` with error `FileSizeExceeded` before reading any body bytes

#### Scenario: Chunked or understated body

- **WHEN** a request omits or understates `Content-Length` and streams more bytes than the limit
- **THEN** the system aborts the moment the running total exceeds the limit and responds `413`

#### Scenario: Multipart overhead headroom

- **WHEN** the request-level limit is computed
- **THEN** it is the configured file-size limit plus 1 MiB of headroom for multipart framing and form fields

#### Scenario: Non-HTTP scope

- **WHEN** the ASGI scope is not `http`
- **THEN** the request passes through unmodified

### Requirement: Edge Controls Are Delegated To The Platform

The system SHALL implement no in-app CORS policy, rate limiting, security headers, or
trusted-host allowlist, and SHALL treat the platform edge as the authoritative place for
them. Any configuration named after those controls has no effect in this service.

#### Scenario: No rate limiting in the application

- **WHEN** a caller issues requests at any rate
- **THEN** the application applies no throttling of its own, and any `429` originates from a downstream provider rather than an in-app limiter

#### Scenario: No CORS policy

- **WHEN** a browser origin calls the API
- **THEN** the application sends no CORS headers, so no cross-origin browser access is permitted by this service

#### Scenario: No security headers

- **WHEN** any response is returned
- **THEN** the application adds no `X-Content-Type-Options`, `X-Frame-Options`, or `Referrer-Policy` headers of its own

#### Scenario: No trusted-host allowlist

- **WHEN** a request arrives with an unexpected `Host` header
- **THEN** the application does not reject it on that basis

#### Scenario: Settings that do not exist

- **WHEN** an operator sets a variable such as `RATE_LIMIT_ENABLED`, `CORS_ALLOWED_ORIGINS`, `SECURITY_HEADERS_ENABLED`, or `TRUSTED_HOSTS`
- **THEN** nothing changes, because no such setting is defined — the value is silently ignored
