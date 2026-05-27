# AIA-424 — Deployment & Data Migration Steps

> **Branch:** `feature/AIA-424-fix-missing-document-type`  
> **Scope:** Introduce `document_category` as schema discriminator; repurpose `document_type` as user-facing classification  
> **Downtime required:** None  
> **Rollback:** Safe — see [Rollback](#5-rollback)

---

## Overview

This PR introduces a two-field model for document classification:

| Field | Role | Values | Stored in |
|---|---|---|---|
| `document_category` | Schema discriminator (code & SQL only) | `"operational"`, `"publication"` | SQL only |
| `document_type` | User-facing classification (filterable) | `"PCR"`, `"Report"`, `"LP"`, `"journal_article"`, … | SQL + AI Search |

The deployment is divided into five ordered phases. Phases 1–2 are automated (migration + code deploy). Phases 3–4 are manual data backfills and can run gradually after the deploy.

---

## Phase 1 — Deploy the Code

### 1.1 Prerequisites

- The branch `feature/AIA-424-fix-missing-document-type` is merged to `main`.
- CI pipeline is green (754 unit tests pass).
- You have credentials to the target environment (dev / staging / prod).

### 1.2 Deploy

Follow the normal container deployment procedure. No special flags are needed.

```bash
# Example: Azure Container Apps deployment
./scripts/deploy_container_app.sh --env dev
```

The new code:
- Accepts `document_type` as an optional user field on upload forms (e.g. `"PCR"`, `"Report"`).
- Injects `document_category = "operational" | "publication"` server-side (hidden from client).
- AI Search indexes and all search/filter routes continue to work with no change to the index schema.

---

## Phase 2 — Run the Alembic Migration

> **Must run AFTER the code deploy** (the new `document_category` column must exist before the app starts writing to it).  
> **Must run BEFORE Phase 3** (Phase 3 reads `document_category`).

### 2.1 Run migration

```bash
uv run alembic upgrade head
```

Or via the migration script if available:

```bash
uv run python scripts/migrate.py
```

### 2.2 What the migration does (`010_add_document_category`)

1. Adds `document_category VARCHAR(100) NULL` column to `file_metadata`.
2. **Back-fills**: `UPDATE file_metadata SET document_category = document_type`  
   (Before this PR, `document_type` held `"operational"` or `"publication"` — exactly what `document_category` needs.)
3. Creates index `ix_metadata_document_category` for efficient filtering.

> ⚠️ The migration does **not** touch `document_type` values. Existing rows will still have `document_type = "operational"` after migration. That is correct — the old value is now stale and will be cleared/replaced in Phase 3.

### 2.3 Verify

```sql
-- Confirm column exists and is populated
SELECT document_category, COUNT(*) 
FROM file_metadata 
GROUP BY document_category;

-- Expected:
-- document_category | count
-- operational       | <N>
-- (any other)       | ...
```

---

## Phase 3 — Backfill `document_type` in SQL  *(optional but recommended)*

> **Can run gradually** after Phase 2. New uploads will immediately use the new schema.  
> Existing documents will have `document_type = "operational"` (old discriminator value) until backfilled.

There are two strategies:

### Option A — Set existing `document_type` to NULL (recommended for clean start)

If your existing operational documents don't have a meaningful specific type yet, set to NULL so they don't appear incorrectly classified:

```sql
-- Clear the stale discriminator value from operational documents
UPDATE file_metadata 
SET document_type = NULL 
WHERE document_category = 'operational';

-- Same for publications
UPDATE file_metadata 
SET document_type = NULL 
WHERE document_category = 'publication';
```

After this, users can classify documents by PATCHing the metadata endpoint:

```bash
PATCH /documents/{file_id}/metadata
{
  "document_type": "PCR"
}
```

### Option B — Map known document types via script

If you have a mapping (e.g. from filename patterns or an external registry), run a classification script:

```python
# scripts/backfill_document_type.py (to be created)
import asyncio
from sqlalchemy import text

KNOWN_MAPPINGS = {
    "PCR": ["project-completion", "pcr-"],
    "LP":  ["lessons-practice", "-lp-"],
    # ...
}

async def classify_by_name(filename: str) -> str | None:
    for doc_type, patterns in KNOWN_MAPPINGS.items():
        if any(p in filename.lower() for p in patterns):
            return doc_type
    return None

# ... iterate file_metadata, apply mappings, UPDATE document_type
```

---

## Phase 4 — Backfill `document_type` in AI Search  *(optional but recommended)*

> **Can run gradually** after Phase 2. Existing AI Search documents will have `metadata/document_type = "operational"` until updated.  
> New uploads will write the correct user-provided value immediately.

### Option A — Re-index affected documents (cleanest, no extra script)

Re-process existing documents through the ingestion pipeline. The pipeline reads `document_type` from SQL (after Phase 3) and writes the updated value to AI Search.

```bash
# Trigger re-ingestion for existing files (depends on your queue/pipeline tooling)
# This re-runs vectorization and writes updated metadata to AI Search
```

### Option B — Direct AI Search partial update (faster, more surgical)

```python
# Pseudocode — iterate SQL, push merge actions to AI Search
async def backfill_search_document_types(search_client, session):
    rows = await session.execute(
        text("SELECT chunk_vector_id, document_type FROM file_metadata fm "
             "JOIN chunk c ON c.file_id = fm.file_id "
             "WHERE fm.document_category = 'operational'")
    )
    actions = [
        {"@search.action": "merge", "id": row.chunk_vector_id,
         "metadata": {"document_type": row.document_type or ""}}
        for row in rows
    ]
    # Upload in batches of 1000
    for i in range(0, len(actions), 1000):
        await search_client.upload_documents(actions[i:i+1000])
```

> ℹ️ The script is idempotent — safe to re-run. A document with `document_type = "operational"` (old stale value) simply has a less-specific classification; it won't cause errors or broken searches.

---

## Phase 5 — Verify End-to-End

### 5.1 Upload a new document with a type

```bash
curl -X POST /documents/upload/operational \
  -F "collection_name=my-collection" \
  -F "ezshare_id=EZSHARE-001" \
  -F "document_type=PCR" \
  -F "file=@my-document.pdf"
```

Check in SQL:

```sql
SELECT file_id, document_category, document_type 
FROM file_metadata 
WHERE ezshare_id = 'EZSHARE-001';

-- Expected:
-- file_id | document_category | document_type
-- <uuid>  | operational       | PCR
```

Check in AI Search — the chunk document should have `metadata/document_type = "PCR"`.

### 5.2 Filter search by document type

```bash
curl -X POST /search/operational \
  -H "Content-Type: application/json" \
  -d '{"query": "transport infrastructure", "document_type": "PCR"}'
```

Response should only include PCR documents.

### 5.3 Create a collection with explicit category

```bash
curl -X POST /collections \
  -H "Content-Type: application/json" \
  -d '{"name": "publications-2024", "document_category": "publication", "vector_dimension": 1536, "embedding_model": "text-embedding-3-small"}'
```

---

## Rollback

The change is **fully reversible** at any phase:

| Phase | Rollback action |
|---|---|
| Phase 1 (code) | Redeploy previous container image |
| Phase 2 (migration) | `uv run alembic downgrade 009` — drops `document_category` column and its index |
| Phase 3 (SQL data) | Restore `document_type = document_category` for affected rows |
| Phase 4 (AI Search) | Re-run ingestion pipeline with old code; AI Search partial-update writes `"operational"` back |

> **Important:** Roll back Phase 4 before Phase 2. If you downgrade the migration while the new code is deployed, the app will fail to find `document_category` and fall back to `OperationalDocumentMetadata` for all documents (safe default, but metadata model selection will be wrong).

---

## Summary Checklist

```
[ ] 1. Merge PR into main
[ ] 2. CI passes (754 unit tests)
[ ] 3. Deploy new container image to target environment
[ ] 4. Run: uv run alembic upgrade head
[ ] 5. Verify: document_category column populated in file_metadata
[ ] 6. (Optional) Run SQL backfill for document_type values
[ ] 7. (Optional) Re-index or direct-update AI Search document_type values
[ ] 8. Smoke test: upload document with document_type, verify in SQL and AI Search
[ ] 9. Smoke test: filter search by document_type
```
