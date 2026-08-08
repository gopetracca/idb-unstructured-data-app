# Security & Authentication

**Target Audience:** Engineers, security reviewers, operators
**Last Updated:** 2026-08-08 (AIA-675)
**Navigation:** [Design Doc](01-design-doc.md) | [Architecture](02-architecture.md) | [API Reference](04-api-and-interfaces.md) | Security & Auth | [Deployment & Operations](07-deployment-and-operations.md)

> **Scope note.** This document describes the security posture **as currently implemented on `develop`** plus the remaining hardening backlog. The [Hardening Roadmap](#hardening-roadmap) shows the exact status of each item (✅ implemented / 🟡 partial / 🔵 designed). Do not assume a control is active unless this document says it is.

---

## Table of Contents

1. [Threat Model & Trust Boundaries](#1-threat-model--trust-boundaries)
2. [Authentication (Entra ID / JWT)](#2-authentication-entra-id--jwt)
3. [JWKS Handling & Token Validation Hardening](#3-jwks-handling--token-validation-hardening)
4. [Authorization (Scope Model)](#4-authorization-scope-model)
5. [Endpoint → Scope Matrix](#5-endpoint--scope-matrix)
6. [Tenant Isolation](#6-tenant-isolation)
7. [Edge Protections (CORS, Rate Limiting, Headers, Hosts)](#7-edge-protections)
8. [Secrets & Managed Identity](#8-secrets--managed-identity)
9. [Fail-Open vs Fail-Closed](#9-fail-open-vs-fail-closed)
10. [Configuration Reference](#10-configuration-reference)
11. [Hardening Roadmap](#hardening-roadmap)

---

## 1. Threat Model & Trust Boundaries

The API is an internal IDB service that ingests documents and serves semantic search. The primary assets are (a) document content and extracted text in Blob Storage, (b) metadata in SQL Server, and (c) vectors in Azure AI Search.

**Trust boundaries:**

```
                       ┌─────────────────────────────────────────────┐
   Caller (M2M / SPA)  │  Platform edge (APIM / Front Door) [external]│
        │  Bearer JWT  │   - TLS termination                          │
        ▼              │   - WAF, authoritative rate limiting         │
  ┌──────────────┐     └───────────────────────┬─────────────────────┘
  │  Entra ID    │ issues                       │
  │  (token IdP) │ RS256 JWT                    ▼
  └──────────────┘             ┌──────────────────────────────────┐
                               │  FastAPI app (this service)      │
                               │  - JWT validation (JWKS)         │
                               │  - scope check per route         │
                               │  - in-app edge safety nets       │
                               │  - server-side tenant resolution │
                               └───────┬──────────────────────────┘
                                       ▼
              Blob Storage · SQL Server · AI Search · OpenAI · Doc Intelligence
              (reached via Managed Identity where supported)
```

**Key principles in force today:**

- **Authentication is performed in-app** against Microsoft Entra ID, not delegated to a gateway. The app validates the JWT signature, issuer, audience, and lifetime itself.
- **Authorization is per-route**, declared with FastAPI `Security(..., scopes=[...])` and checked by exact match against the **union** of the token's `roles` and `scp` claims.
- **Tenant is resolved server-side.** Clients can no longer choose their tenant (see [§6](#6-tenant-isolation)).
- **Authoritative throttling/WAF belongs at the platform edge**, and today it is the *only* place they exist — there are no in-app edge protections ([§7](#7-edge-protections)).

---

## 2. Authentication (Entra ID / JWT)

Authentication is implemented in `src/presentation/http/auth/`:

| File | Responsibility |
|------|----------------|
| `dependencies.py` | `get_current_user` FastAPI dependency — the single entry point every protected route uses |
| `token_validator.py` | `TokenValidator` — verifies signature and claims of a bearer token |
| `jwks_client.py` | `JwksClient` — fetches and caches Entra ID signing keys (JWKS) |
| `models.py` | `CurrentUser` — resolved identity (`user_id`, `tenant_id`, `email`, `roles`) |
| `errors.py` | `AuthenticationError` (401), `AuthorizationError` (403) |

### Token flow

1. Caller obtains an OAuth2 access token from Entra ID for this API's audience (`api://{client_id}` or an explicit override).
2. Caller sends `Authorization: Bearer <jwt>`.
3. `get_current_user` (`dependencies.py:30`) runs as a dependency on the route:
   - If `ENTRA_ID_ENABLED=false` → returns a synthetic anonymous user (see [§9](#9-fail-open-vs-fail-closed)).
   - Otherwise → requires credentials, calls `TokenValidator.validate`, then checks scopes.
4. On success the route receives a `CurrentUser`.

### What `TokenValidator.validate` checks (`token_validator.py`)

- **Algorithm:** RS256 **only** (no `none`, no HS256 downgrade).
- **Signature:** verified against the JWKS public key whose `kid` matches the token header (`RSAAlgorithm.from_jwk`).
- **Issuer (`iss`):** pinned to `https://login.microsoftonline.com/{tenant_id}/v2.0`.
- **Audience (`aud`):** must match one of `EntraIDSettings.accepted_audiences` — **both** `api://{client_id}` and the bare `{client_id}`, because a v2 token carries the bare GUID. An explicit `ENTRA_ID_AUDIENCE` narrows this to that one value.
- **Lifetime (`exp`, `nbf`):** enforced with a 30-second clock-skew leeway.
- **Optional client allowlist:** when `ENTRA_ID_ALLOWED_CLIENT_IDS` is non-empty, the caller's `azp`/`appid` claim must be in the list (defense-in-depth for M2M).
- **Required identity claims:** `oid` and `tid` must be present and non-empty; otherwise the request is rejected as **401** (not 500). See [§3](#3-jwks-handling--token-validation-hardening).

> **App-only (M2M) and delegated both work.** Authorization reads the **union** of the `roles` claim
> (Entra App Roles, app-only callers) and the `scp` claim (delegated scopes, user and on-behalf-of
> callers), so a single code path serves both — see [§4](#4-authorization-scope-model).

---

## 3. JWKS Handling & Token Validation Hardening

Implemented under **AIA-675**.

`JwksClient` (`jwks_client.py`) caches signing keys keyed by `kid`:

- **Cache TTL:** `ENTRA_ID_JWKS_CACHE_TTL_SECONDS` (default **3600s**).
- **Refresh-on-unknown-kid:** if a token presents a `kid` not in cache (e.g. after Entra key rotation), the client forces a refresh — **but** forced refreshes are throttled by `ENTRA_ID_JWKS_FORCE_REFRESH_MIN_INTERVAL_SECONDS` (default **60s**). This closes a DoS-amplification vector where a flood of tokens carrying bogus `kid`s could otherwise drive unbounded outbound JWKS fetches.
- **Concurrency:** an `asyncio.Lock` prevents a refresh stampede — concurrent requests that miss the cache wait on one in-flight fetch.

- **Cold-start correctness.** Both timestamps are seeded with `-inf`, not `0.0`. `time.monotonic()`
  counts from an arbitrary origin (host uptime on Linux), so a `0.0` sentinel makes a freshly booted
  node look "fresh", skip its first fetch, and — with the throttle also blocking the fallback —
  reject every token as "Unknown signing key" until uptime exceeds the TTL.

Two correctness/robustness fixes also landed under AIA-675:

- **Defensive claim reads.** `oid`/`tid` are read with `.get(...)` and validated; a validly-signed token missing them yields **401**, not an unhandled `KeyError` → 500.
- **Token v2 expectation.** The issuer is pinned to the `/v2.0` endpoint, and the dev registration sets `requestedAccessTokenVersion: 2`. Note the audience consequence described in [§2](#2-authentication-entra-id--jwt).

---

## 4. Authorization (Scope Model)

The legacy `api.read` / `api.write` / `api.admin` model is **gone**. Authorization uses a
resource-oriented **4-permission** model, centralised in `auth/scopes.py`:

| Permission | Covers |
|-------|--------|
| `Search` | all `/search/*` |
| `documents.read` | all GET reads + `/capabilities` |
| `documents.write` | uploads, PATCH, pipeline triggers (contents/chunks/embeddings POST) |
| `admin` | all DELETEs + entire `/collections/*` + entire `/analytics/*` |

Verb rule of thumb: `GET → documents.read`, `POST/PATCH → documents.write`, `DELETE → admin`.

### Two claims, two spellings

Entra carries authorization in a different claim depending on how the token was obtained, and this
API has live consumers of **both**:

- **Delegated scopes** → the **`scp`** claim (a space-delimited *string*). Issued only when a user is
  in the flow — including the on-behalf-of exchange the MCP server performs. This is the only model
  available to OBO.
- **App Roles** → the **`roles`** claim (an array). The only model available to app-only /
  client-credentials callers, which never receive `scp`.

`get_current_user` authorizes on the **union** of both (`dependencies.granted_scopes`).

> ⚠️ **Entra forbids one permission `value` in both `appRoles` and `oauth2PermissionScopes`** on a
> single application — it returns `DuplicateValue`. Each permission therefore has two spellings,
> following the Microsoft Graph convention in which application permissions carry a `.All` suffix:

| Caller | Flow | Claim | Literal to request |
|---|---|---|---|
| User / on-behalf-of (the MCP) | auth code, OBO | `scp` | `Search`, `documents.read`, `documents.write`, `admin` |
| Application / service | client credentials | `roles` | `Search.All`, `documents.read.All`, `documents.write.All`, `admin.All` |

Routes declare the **delegated** spelling; `accepted_literals()` expands it to include the App Role
twin, so one declaration serves both caller types.

### No scope implication

The check is **exact membership, no hierarchy**. `admin` does **not** confer `documents.read`, and
`documents.read.All` does not satisfy `documents.write`. Expanding a permission to its `.All` twin
is not implication — both spellings denote the *same* permission under different Entra models.
Principals needing several permissions are granted each one in Entra; bundling lives there (assign a
security group to multiple App Roles), never in code.

> **`Search` is compatibility-critical.** It exists as a *delegated scope* and the MCP server holds
> an admin-consented grant for it. It must never be renamed or removed. An earlier revision of this
> document and of `scopes.py` claimed `Search` was an App Role — it never was (AIA-675).

---

## 5. Endpoint → Scope Matrix

Extracted from the **deployed OpenAPI schema** on 2026-08-08 — this is what the running service
enforces, not a transcription of the source. Each row shows the **delegated** spelling the route
declares; the corresponding `.All` App Role satisfies it equally (see [§4](#4-authorization-scope-model)).

| Method & path | Permission |
|---|---|
| `GET /` (liveness alias) | _none_ — probe |
| `GET /health/live` | _none_ — probe |
| `GET /health/ready` | _none_ — probe |
| `GET /api/v1/capabilities` | `documents.read` |
| `POST /api/v1/documents` *(deprecated generic upload)* | `documents.write` |
| `POST /api/v1/documents/operational` | `documents.write` |
| `POST /api/v1/documents/publication` | `documents.write` |
| `GET /api/v1/documents` (list) | `documents.read` |
| `GET /api/v1/documents/{id}` | `documents.read` |
| `PATCH /api/v1/documents/{id}` | `documents.write` |
| `DELETE /api/v1/documents/{id}` | `admin` |
| `POST /api/v1/contents` | `documents.write` |
| `GET /api/v1/contents` · `GET /{id}` · `GET /{id}/text` | `documents.read` |
| `DELETE /api/v1/contents/{id}` | `admin` |
| `POST /api/v1/chunks` | `documents.write` |
| `GET /api/v1/chunks` · `GET /{id}` | `documents.read` |
| `DELETE /api/v1/chunks/{id}` | `admin` |
| `POST /api/v1/embeddings` | `documents.write` |
| `GET /api/v1/embeddings` · `GET /{id}` | `documents.read` |
| `DELETE /api/v1/embeddings/{id}` | `admin` |
| `POST /api/v1/search` *(deprecated generic)* | `Search` |
| `POST /api/v1/search/operational` | `Search` |
| `POST /api/v1/search/publications` | `Search` |
| `GET` · `POST` · `DELETE /api/v1/collections/*` (entire surface, incl. reranker and ingest) | `admin` |
| `GET /api/v1/documents/{file_id}/processing-timeline` | `admin` |
| `GET /api/v1/analytics/stage-durations` | `admin` |

The three probe endpoints are the **only** unauthenticated operations, and that invariant is pinned
by `tests/unit/presentation/http/test_security_contract.py`, which enumerates every mounted
operation and fails if a non-allowlisted route lacks a security requirement.
`tests/unit/presentation/http/test_route_scopes.py` pins the exact permission of each route, so
drift fails the build rather than shipping silently.

> `src/presentation/http/routes/documents.py` exists but is **not registered** in `main.py` (superseded by `document_management.py` and the split upload routers). It is not part of the live surface.

---

## 6. Tenant Isolation

**Implemented (AIA-476).** ✅

The API no longer accepts a client-supplied tenant. The `X-Tenant-Id` header, the `tenant_id` query
parameter and the body `tenant_id` field are all gone from the surface — verified by contract tests
that assert no operation exposes a tenant parameter and no request-body schema exposes `tenant_id`.

The effective tenant is resolved server-side in `src/presentation/http/tenant.py`:

```python
def get_effective_tenant_id() -> str:
    return get_settings().default_tenant_id   # DEFAULT_TENANT_ID, default "default"
```

- Routes declare `tenant_id: TenantId` and never read a client header for tenancy.
- The **multi-tenant plumbing in use-cases and repositories is preserved**. To re-enable per-user multi-tenancy later, change `get_effective_tenant_id()` to return `CurrentUser.tenant_id` (the `tid` claim) — **no route signatures change**.
- Storage layout remains tenant-scoped (`{container}/{tenant_id}/{file_id}/...`) and **stays 1 blob per chunk** (an intentional decision; do not consolidate to 1 blob per file).

---

## 7. Edge Protections

**Tracked as [AIA-483](https://iadb-ttd.atlassian.net/browse/AIA-483) — 🔵 designed, NOT implemented.**

> ⚠️ **Correction (2026-08-08).** A previous revision of this document listed
> `SECURITY_HEADERS_ENABLED`, `CORS_ALLOWED_ORIGINS`, `TRUSTED_HOSTS` and `RATE_LIMIT_*` as
> "pre-defined in `src/config/settings.py`". **They do not exist.** Neither the settings nor
> `middleware/edge.py` are in the codebase. Setting those variables today has no effect whatsoever.

The design below is the intended shape when AIA-483 is picked up. Until then **there are no in-app
edge protections at all**: no CORS policy, no rate limiting, no security headers, no trusted-host
allowlist. Authoritative controls belong at the platform edge (APIM / Front Door) regardless; treat
any future in-app implementation as a coarse safety net, since it cannot coordinate across replicas.

| Protection | Planned setting(s) | Planned default | Intended behavior |
|---|---|---|---|
| **Security headers** | `SECURITY_HEADERS_ENABLED` | on | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`. HSTS omitted (TLS terminates at the edge). |
| **Rate limiting** | `RATE_LIMIT_ENABLED`, `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW_SECONDS` | off | Sliding-window, per-replica, keyed on client IP. Throttles `/api/v1/search` prefixes. `429` + `Retry-After`. |
| **Trusted hosts** | `TRUSTED_HOSTS` | off | `TrustedHostMiddleware` allowlist on the `Host` header. |
| **CORS** | `CORS_ALLOWED_ORIGINS` | off | Exact-match origin allowlist. Empty = no browser origin allowed. |

The one request-shaping control that **is** implemented is `MaxBodySizeMiddleware` (AIA-478): it
returns `413` on an oversized declared `Content-Length` before the body is buffered, and counts
bytes on the stream to catch chunked or understated bodies. It is bounded by
`FILE_UPLOAD_MAX_FILE_SIZE_MB`.

---

## 8. Secrets & Managed Identity

**Preferred posture (Azure):** use **Managed Identity** instead of keys wherever the SDK supports it.

- **Storage:** set `AZURE_STORAGE_ACCOUNT_NAME` (and leave the connection string at its dev default). Clients then use `DefaultAzureCredential` against `https://{account}.{blob,queue}.core.windows.net`. Pin the identity with `AZURE_CLIENT_ID` (user-assigned MI).
- **Document Intelligence / Embeddings / AI Search:** `api_key` is **optional** — `is_configured` only requires the endpoint, so these adapters work under managed identity when no key is supplied.
- **ACR pulls:** grant the Container App's managed identity `AcrPull` and configure `az containerapp registry set --identity system` (see [Deployment & Operations](07-deployment-and-operations.md)).

**Secrets hygiene gaps (issue #152 — tracked, not yet fully closed):**

- `api_key` / `connection_string` / `database_url*` are currently plain `str` in `settings.py`, not `SecretStr`. They can therefore appear in `repr(settings)` / logs.
- `settings.py` has a `print(settings)` under `if __name__ == "__main__":` (line ~702) — harmless as a module guard, but do **not** add settings dumps to startup/log paths.
- **Direction:** wrap secret-bearing fields in `pydantic.SecretStr`; prefer/enforce managed identity in prod; never log a settings object.
- **SQL access is parameterized** (no SQL injection); list filters use a **column allowlist** in `_apply_filters`.

---

## 9. Fail-Open vs Fail-Closed

**Fail-closed (AIA-482).** ✅ Implemented in `main.verify_auth_configuration()`, which runs first in
the FastAPI lifespan — before any dependency setup — and raises `AuthConfigurationError` on:

1. **Auth disabled outside development.** `ENTRA_ID_ENABLED` still defaults to `false`, and when
   disabled `get_current_user` returns `_ANONYMOUS_USER` carrying every permission. A deploy that
   forgets the variable would serve the whole API unauthenticated, so the app refuses to start
   instead.
2. **Auth enabled but incomplete.** Without both `ENTRA_ID_TENANT_ID` and `ENTRA_ID_CLIENT_ID` the
   validator cannot build an issuer, JWKS URI or audience, so every request would `401`. Fails at
   startup rather than at request time.

`ALLOW_ANONYMOUS_AUTH=true` is the explicit escape hatch for running a non-development build
locally. **Never set it in a deployed environment.**

> ⚠️ **The guard is only armed where `ENVIRONMENT` says so.** It is currently **unset** on the
> Container Apps, so `environment` defaults to `dev`, `is_development` is true, and the guard will
> not fire. Dev is protected today because `ENTRA_ID_ENABLED=true` is set explicitly — not by this
> guard. **Set `ENVIRONMENT` per environment (`test`, `prod`) to arm it**, and keep
> `ENTRA_ID_ENABLED=true` in the release checklist regardless.

**This was not hypothetical.** Before AIA-675 the dev Container App had no `ENTRA_ID_*` variables at
all and `GET /api/v1/documents` returned `200` with document data to an unauthenticated caller from
the public internet.

---

## 10. Configuration Reference

Entra ID settings (`EntraIDSettings`, env prefix `ENTRA_ID_`):

| Env var | Default | Meaning |
|---|---|---|
| `ENTRA_ID_ENABLED` | `false` | Master switch. **Must be `true` in prod.** |
| `ENTRA_ID_TENANT_ID` | `""` | Azure AD tenant GUID; pins `iss` and JWKS URI. |
| `ENTRA_ID_CLIENT_ID` | `""` | API app registration client ID. |
| `ENTRA_ID_AUDIENCE` | `""` | Explicit audience override. When empty, **both** `api://{client_id}` and the bare `{client_id}` are accepted — see the note below. |
| `ENTRA_ID_JWKS_CACHE_TTL_SECONDS` | `3600` | JWKS cache lifetime. |
| `ENTRA_ID_JWKS_FORCE_REFRESH_MIN_INTERVAL_SECONDS` | `60` | Unknown-`kid` forced-refresh throttle (DoS guard). |
| `ENTRA_ID_ALLOWED_CLIENT_IDS` | `[]` | JSON array; optional `azp`/`appid` allowlist. Empty = allow any valid-audience caller. |

> **Audience gotcha.** The app registration sets `requestedAccessTokenVersion: 2`, so Entra issues
> `aud` as the **bare client ID**, not `api://{client_id}`. Both forms are accepted by default for
> exactly this reason. Setting `ENTRA_ID_AUDIENCE` to the wrong one of the two will `401` every
> request with `Invalid token audience` and no other clue.

Tenant & startup settings (root `Settings`):

| Env var | Default | Meaning |
|---|---|---|
| `DEFAULT_TENANT_ID` | `default` | Effective tenant for all requests (server-resolved). |
| `ENVIRONMENT` | `dev` | Deployment environment. Arms the fail-closed guard when it is not a development value. |
| `ALLOW_ANONYMOUS_AUTH` | `false` | Permit running with auth disabled outside development. Never set in a deployed environment. |

> The edge settings previously listed here (`SECURITY_HEADERS_ENABLED`, `CORS_ALLOWED_ORIGINS`,
> `TRUSTED_HOSTS`, `RATE_LIMIT_*`) **do not exist** — see [§7](#7-edge-protections).

---

## Hardening Roadmap

Status of the security workstream as of **2026-08-08**, verified against `develop` and the deployed
dev revision.

| Item | Jira | Status |
|---|---|---|
| Secure open endpoints; remove `/echo` test endpoints | AIA-477 | ✅ **Implemented** — contract test pins that only the three probes are unauthenticated |
| Server-side tenant resolution (no client-supplied tenant) | AIA-476 | ✅ **Implemented** (`http/tenant.py`) |
| Resource-oriented 4-permission model | AIA-481 | ✅ **Implemented** (`auth/scopes.py`) — corrected by AIA-675 |
| `scp` ∪ `roles` authorization; dual `.All` spelling; audience fix | AIA-675 | ✅ **Implemented** (`auth/dependencies.py`, `auth/scopes.py`) |
| JWKS refresh throttle, defensive `oid`/`tid` reads, client allowlist | AIA-675 | ✅ **Implemented** (`auth/jwks_client.py`, `auth/token_validator.py`) |
| Fail-closed auth | AIA-482 | ✅ **Implemented** (`main.verify_auth_configuration`) — 🟡 inert until `ENVIRONMENT` is set per environment |
| Bounded/streamed uploads (`413` before buffering) | AIA-478 | ✅ **Implemented** (`middleware/max_body_size.py`) |
| Edge protections: CORS, rate limit, security headers, trusted host | AIA-483 | 🔵 **Designed, not implemented** — settings do **not** exist |
| Secrets as `SecretStr`; enforce managed identity in prod | AIA-484 | 🟡 **Partial** (managed identity supported; `SecretStr` pending) |
| Assign the new `.All` App Roles to machine principals | AIA-675 | 🔵 **Blocked** — requires an Application Administrator |

**Facts every operator must internalize:**

1. **`Search` is a delegated scope, not an App Role**, and the MCP server depends on it. Never rename
   or remove it. Machine callers use `Search.All`.
2. **Delegated scopes are granted by consent; App Roles by assignment.** A user can consent to the
   former themselves; only an Application Administrator can do the latter.
3. **`ENTRA_ID_ENABLED=true` is non-negotiable outside development** — and the fail-closed guard only
   enforces that once `ENVIRONMENT` is set to a non-development value.
4. **No in-app edge protections are active** (CORS, rate limiting, security headers). Rely on
   APIM / Front Door until AIA-483 lands.
5. **Auth precedes body handling** — an unauthenticated request gets `401`, not a validation error,
   even with a malformed body.

For a token, use [`scripts/get_dev_token.ps1`](../scripts/get_dev_token.ps1) — see
[AIA-675](https://iadb-ttd.atlassian.net/browse/AIA-675) for the full remediation record and the
validation evidence.
