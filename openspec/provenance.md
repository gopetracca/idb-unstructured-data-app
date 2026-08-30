# Provenance of the reverse-engineered specs

These specs were extracted from a system that already existed. They describe behaviour as
built, so they carry no record of *why* each behaviour was chosen — that reasoning lives
in the Jira tickets, the merged PRs, and `docs/`.

This file is the index between them. Use it when a requirement looks arbitrary and you
want the argument behind it before changing it.

## Why there are no backfilled change proposals

OpenSpec's `changes/archive/` holds changes that went through the propose → implement →
archive loop. We deliberately did **not** synthesise archive entries for the work below.

- An archived change is a record that a proposal was written and reviewed. Backfilling
  would fabricate that record, and a future reader could not tell a real archived
  decision from a reconstructed one.
- Archived changes are *deltas* against a previous spec state. There was no previous
  state, so every backfilled delta would read "ADDED everything" and convey nothing the
  main spec does not already say.
- The implementation record already exists and is authoritative: git history, the merged
  PRs, the Jira tickets, and `docs/`. A second, reconstructed copy could only drift from
  it.

So the archive starts empty and fills up from here forward with changes that actually
went through the loop. What was worth keeping from the history is either already encoded
as a requirement or indexed below.

## Ticket → capability index

| Ticket | What it changed | Capabilities now carrying it | Rationale lives in |
| --- | --- | --- | --- |
| AIA-75 | Initial function app, hexagonal skeleton | foundational — spread across all | git history |
| AIA-393 | Datadog tracing across the service, JSON log format, SQL log noise filtering | `observability` | commit messages |
| AIA-394 | Database migrations in CD as a pre-deploy Container Apps Job, serialized by a SQL app lock | `metadata-persistence`, `deployment-and-runtime` | `docs/AIA-394-database-migrations.md` |
| AIA-397 | Enriched operational search response metadata; dropped `text_preview` | `search` | commit messages |
| AIA-414 | Document deletion across blobs, vector index, and SQL | `document-management` | commit messages |
| AIA-416 | Chunker made offline-safe inside the Azure VNet (tokenizer cache warmed at build, HF downloads blocked) | `document-chunking`, `deployment-and-runtime` | code comments in `chunker_chonkie.py`, `Dockerfile` |
| AIA-424 | `document_type` repurposed as a user-facing label; `document_category` introduced as the schema discriminator | `index-schema-registry`, `document-upload`, `document-management` | `docs/AIA-424-deployment-steps.md` |
| AIA-476 | Stopped accepting a client-supplied tenant | `tenant-resolution` | module docstring in `tenant.py`, `docs/06-security-and-auth.md` §6 |
| AIA-477 | Secured open endpoints; removed leftover test endpoints; added the auth guard test | `authentication-authorization` | `tests/unit/presentation/http/test_security_contract.py` |
| AIA-478 | Bounded and streamed uploads; 413 before buffering | `edge-protection`, `document-upload` | module docstring in `middleware/max_body_size.py` |
| AIA-479 | Liveness / readiness split and Container Apps probe configuration | `health-and-readiness`, `deployment-and-runtime` | module docstring in `routes/health.py`, `scripts/containerapp_probes.py` |
| AIA-481 | Resource-oriented four-permission authorization model | `authentication-authorization` | module docstring in `auth/scopes.py`, `docs/06-security-and-auth.md` §4–5 |
| AIA-482 | Fail-closed startup guard on unsafe auth configuration | `authentication-authorization` | `verify_auth_configuration` docstring, `docs/06-security-and-auth.md` §9 |
| AIA-483 | Edge protections **designed, not implemented** — no in-app CORS, rate limiting, security headers, or trusted hosts | `edge-protection` | `docs/06-security-and-auth.md` §7 |
| AIA-675 | Entra authorization working end to end against the real app registration; JWKS cold-start fix; dual permission spellings; token helper scripts | `authentication-authorization`, `local-development` | `auth/scopes.py`, `auth/jwks_client.py`, `docs/06-security-and-auth.md` |

## Known gaps recorded rather than fixed

Behaviour the specs describe accurately but that is worth revisiting. Each is a candidate
for a real change proposal.

- **Unconfigured Azure dependencies fall back to fakes silently** (`adapter-selection`).
  A deploy missing `EMBEDDING_ENDPOINT` indexes fabricated vectors and still reports
  ready; a startup warning is the only signal.
- **Storage provisioning is best-effort and cannot detect its own failure**
  (`pipeline-orchestration`). The create-if-not-exists helpers catch every exception and
  return the same result as "already existed", so the "ensured" log line is not evidence.
- **The fail-closed auth guard is inert unless `ENVIRONMENT` is set**
  (`authentication-authorization`). It defaults to `dev`, which is treated as
  development.
- **No in-app edge protections** (`edge-protection`), tracked as AIA-483.
- **Secret-bearing settings are plain strings**, so they can appear in a settings `repr`.
  Tracked outside these specs; see `docs/06-security-and-auth.md` §8.
