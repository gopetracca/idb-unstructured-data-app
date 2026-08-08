# API Reference: EA Unstructured Data API

**Target Audience:** API consumers, integration engineers
**Last Updated:** 2026-02-01
**Navigation:** [Design Doc](01-design-doc.md) | [Architecture](02-architecture.md) | API Reference

---

## Table of Contents

1. [API Overview](#api-overview)
2. [Document Management Endpoints](#document-management-endpoints)
3. [Search Endpoints](#search-endpoints)
4. [Collection Management Endpoints](#collection-management-endpoints)
5. [RAG Pipeline Endpoints](#rag-pipeline-endpoints)
6. [System Information Endpoints](#system-information-endpoints)
7. [Error Handling](#error-handling)

---

## API Overview

### Base URL

```
https://{function-app-name}.azurewebsites.net
```

For local development:
```
http://localhost:7071
```

### Authentication

All `/api/v1/*` endpoints require a Microsoft Entra ID bearer token **and** a
specific permission. The API uses a resource-oriented 4-permission model:

| Permission | Grants |
|-------|--------|
| `Search` | `POST /api/v1/search`, `/search/operational`, `/search/publications` |
| `documents.read` | All GET reads (documents, contents, chunks, embeddings) and `/capabilities` |
| `documents.write` | Uploads, metadata PATCH, pipeline triggers (contents/chunks/embeddings POST) |
| `admin` | All DELETEs, the entire `/collections/*` surface, and `/analytics/*` |

Verb rule of thumb: GET → `documents.read`, POST/PATCH → `documents.write`,
DELETE → `admin`; plus `Search` for `/search/*` and `admin` for
`/collections/*` and `/analytics/*`.

#### Two spellings per permission

Each permission exists in the app registration twice, because Entra rejects a
permission `value` that appears in both `appRoles` and `oauth2PermissionScopes`
on the same application (`DuplicateValue`). Following the Microsoft Graph
convention, the application-permission variant carries a `.All` suffix:

| Caller | Flow | Claim | Literal to request |
|---|---|---|---|
| User / on-behalf-of (e.g. the MCP server) | auth code, OBO | `scp` | `Search`, `documents.read`, … |
| Application / service | client credentials | `roles` | `Search.All`, `documents.read.All`, … |

The API authorizes on the **union** of `roles` and `scp`, and treats a
permission and its `.All` twin as the same permission. A route therefore
declares one requirement and serves both caller types.

> **Client credentials cannot obtain `scp`.** Delegated scopes are only issued
> when a user is in the flow. A daemon must be assigned the `.All` App Role.

There is **no scope implication**: `admin` does not include `documents.read`.
Principals needing multiple permissions are assigned each one in Entra
(e.g. an operator gets `admin` + `documents.write` + `documents.read` +
`Search`). Responses: `401` for a missing/invalid token, `403` for a
valid token lacking the required permission. When `ENTRA_ID_ENABLED=false`
(dev/CI only) all requests are accepted anonymously with every permission —
the app **refuses to start** with auth disabled outside a development
environment unless `ALLOW_ANONYMOUS_AUTH=true` is set explicitly.

#### Audience

The app registration uses `requestedAccessTokenVersion: 2`, so Entra issues
`aud` as the **bare client ID**, not `api://{client_id}`. Both forms are
accepted; set `ENTRA_ID_AUDIENCE` only to pin validation to one exact value.

### Health Probes

Unauthenticated endpoints used by Azure Container Apps probes (configured by
`scripts/deploy_container_app.{sh,ps1} --configure-probes`):

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `GET /health/live` | Liveness — process is up, no dependency I/O | `200 {"status": "alive", ...}` |
| `GET /health/ready` | Readiness/startup — SQL Server + Azure AI Search checked concurrently (4s timeout each) | `200` when all pass; `503` with a per-dependency `checks` map otherwise |

`GET /` remains as a legacy liveness alias.

### Common Headers

| Header | Required | Description | Example |
|--------|----------|-------------|---------|
| `Content-Type` | Yes (POST/PATCH) | Request content type | `application/json` or `multipart/form-data` |
| `Authorization` | Yes | Bearer token | `Bearer {token}` |

### Response Format

All endpoints return JSON responses with consistent structure:

**Success Response:**
```json
{
  "field1": "value1",
  "field2": "value2"
}
```

**Error Response:**
```json
{
  "error": "ErrorType",
  "message": "Human-readable error message",
  "details": {
    "additional": "context"
  },
  "correlation_id": "abc-123-def"
}
```

### Common HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | OK - Request succeeded |
| 201 | Created - Resource created successfully |
| 202 | Accepted - Request accepted for processing |
| 400 | Bad Request - Invalid request parameters |
| 404 | Not Found - Resource not found |
| 409 | Conflict - Resource already exists |
| 429 | Too Many Requests - Rate limit exceeded |
| 500 | Internal Server Error - Server-side error |
| 503 | Service Unavailable - Service not initialized |

---

## Document Management Endpoints

### Upload Document

Upload a PDF or Word document with metadata for RAG processing.

**Endpoint:** `POST /api/v1/documents`

**Request:**
- Content-Type: `multipart/form-data`

**Form Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | File | Yes | PDF or Word document to upload |
| `collection_name` | string | Yes | Target collection for document ingestion |
| `ezshare_id` | string | Yes | External document ID (e.g., EZSHARE-510177122-450). Must be unique per tenant. |
| `metadata` | string (JSON) | No | Optional JSON metadata object |
| `chunking_strategy_name` | string | No | Strategy name: `fixed_size` (default), `semantic_chunking`, `markdown_aware`, `recursive_chunking` |
| `chunking_parameters` | string (JSON) | No | Parameters JSON. Default/example: `{"chunk_size": 512, "chunk_overlap": 50}`. Optional keys by strategy: `separator`, `respect_sentences`, `respect_code_blocks`, `max_header_depth`, `separators`. |

**Metadata Schema (JSON string):**
```json
{
  "document_type": "report",
  "tags": ["annual", "2024"],
  "author": "John Smith",
  "department": "Operations",
  "language": "en",
  "description": "Q4 2024 Financial Report",
  "operation_number": "UR-P1180",
  "country": "Uruguay",
  "sector": "TRANSPORT",
  "disclosed": true,
  "year": 2024,
  "operation_type": "Loan",
  "dept_id": "INE/TSP",
  "document_author": "Jane Doe",
  "file_extension": ".pdf",
  "access_to_information_policy": "public",
  "document_publish_date": "2024-12-31T00:00:00Z",
  "document_name": "Annual Report 2024"
}
```

**Response:** `201 Created`

```json
{
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "annual-report-2024.pdf",
  "size_bytes": 1048576,
  "mime_type": "application/pdf",
  "uploaded_at": "2026-01-30T10:00:00Z",
  "metadata": {
    "document_type": "report",
    "tags": ["annual", "2024"],
    "author": "John Smith",
    "department": "Operations",
    "language": "en",
    "version": 1,
    "status": "uploaded",
    "page_count": null,
    "word_count": null,
    "chunk_count": null,
    "indexed_at": null
  }
}
```

**Example:**

```bash
curl -X POST "https://{app}.azurewebsites.net/api/v1/documents" \
  -H "Authorization: Bearer {token}" \
  -H "X-Tenant-ID: default" \
  -F "file=@/path/to/document.pdf" \
  -F "collection_name=embeddings" \
  -F "ezshare_id=EZSHARE-510177122-450" \
  -F "chunking_strategy_name=markdown_aware" \
  -F 'chunking_parameters={"chunk_size":1200,"chunk_overlap":100,"respect_code_blocks":true,"max_header_depth":4}' \
  -F 'metadata={"document_type":"report","tags":["annual","2024"],"author":"John Smith"}'
```

---

### Get Document

Retrieve a single document by ID.

**Endpoint:** `GET /api/v1/documents/{id}`

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | string (UUID) | Document file ID |

**Response:** `200 OK`

```json
{
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "annual-report-2024.pdf",
  "size_bytes": 1048576,
  "mime_type": "application/pdf",
  "created_at": "2026-01-30T10:00:00Z",
  "updated_at": "2026-01-30T11:00:00Z",
  "metadata": {
    "document_type": "report",
    "tags": ["annual", "2024"],
    "author": "John Smith",
    "department": "Operations",
    "language": "en",
    "version": 2,
    "status": "indexed",
    "page_count": 45,
    "word_count": 12500,
    "chunk_count": 32,
    "indexed_at": "2026-01-30T10:15:00Z"
  }
}
```

**Example:**

```bash
curl -X GET "https://{app}.azurewebsites.net/api/v1/documents/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer {token}" \
  -H "X-Tenant-ID: default"
```

---

### Update Document Metadata

Update metadata for an existing document using PATCH semantics (partial updates).

**Endpoint:** `PATCH /api/v1/documents/{id}`

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | string (UUID) | Document file ID |

**Request Body:**

```json
{
  "document_type": "policy",
  "tags": ["updated", "2024"],
  "author": "Jane Doe",
  "department": "Legal",
  "language": "es",
  "description": "Updated description"
}
```

All fields are optional. Only provided fields will be updated.

**Response:** `200 OK`

```json
{
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "annual-report-2024.pdf",
  "updated_at": "2026-01-30T12:00:00Z",
  "metadata": {
    "document_type": "policy",
    "tags": ["updated", "2024"],
    "author": "Jane Doe",
    "department": "Legal",
    "language": "es",
    "description": "Updated description",
    "version": 3,
    "status": "indexed"
  }
}
```

**Example:**

```bash
curl -X PATCH "https://{app}.azurewebsites.net/api/v1/documents/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer {token}" \
  -H "X-Tenant-ID: default" \
  -H "Content-Type: application/json" \
  -d '{"document_type":"policy","tags":["updated","2024"]}'
```

---

### Delete Document

Delete a document from the RAG system.

**Endpoint:** `DELETE /api/v1/documents/{id}`

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | string (UUID) | Document file ID |

**Response:** `200 OK`

```json
{
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "annual-report-2024.pdf",
  "deleted_at": "2026-01-30T13:00:00Z",
  "message": "Document successfully deleted"
}
```

**Example:**

```bash
curl -X DELETE "https://{app}.azurewebsites.net/api/v1/documents/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer {token}" \
  -H "X-Tenant-ID: default"
```

---

### List Documents

List documents with filtering, sorting, and pagination support.

**Endpoint:** `GET /api/v1/documents`

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Items per page (1-100, default: 20) |
| `cursor` | string | No | Pagination cursor for next/previous page |
| `sort_by` | string | No | Sort field: `created_at`, `updated_at`, `filename`, `operation_number`, `year`, `country`, `sector` (default: `created_at`) |
| `sort_order` | string | No | Sort order: `asc`, `desc` (default: `desc`) |

**Filter Parameters (JSON Metadata - in-memory filtering):**

| Parameter | Type | Description |
|-----------|------|-------------|
| `document_type` | string | Filter by document type |
| `tags` | string | Filter by tags (comma-separated, AND logic) |
| `source` | string | Filter by source |
| `department` | string | Filter by department |

**Filter Parameters (Promoted Fields - server-side in metadata storage):**

| Parameter | Type | Description |
|-----------|------|-------------|
| `operation_number` | string | Filter by operation number (e.g., UR-P1180) |
| `country` | string | Filter by country |
| `sector` | string | Filter by sector (e.g., TRANSPORT) |
| `disclosed` | boolean | Filter by disclosure status |
| `year` | integer | Filter by exact year |
| `year_min` | integer | Filter by minimum year (inclusive) |
| `year_max` | integer | Filter by maximum year (inclusive) |
| `operation_type` | string | Filter by operation type |
| `dept_id` | string | Filter by department ID (e.g., INE/TSP) |
| `document_author` | string | Filter by document author (partial match) |
| `file_extension` | string | Filter by file extension (e.g., .pdf, pdf) |
| `access_to_information_policy` | string | Filter by access policy |
| `ezshare_id` | string | Filter by EZSHARE ID |

**Response:** `200 OK`

```json
{
  "documents": [
    {
      "file_id": "550e8400-e29b-41d4-a716-446655440000",
      "filename": "annual-report-2024.pdf",
      "size_bytes": 1048576,
      "mime_type": "application/pdf",
      "created_at": "2026-01-30T10:00:00Z",
      "updated_at": "2026-01-30T11:00:00Z",
      "metadata": {
        "document_type": "report",
        "tags": ["annual", "2024"],
        "author": "John Smith",
        "department": "Operations",
        "language": "en",
        "version": 1,
        "status": "indexed"
      }
    }
  ],
  "pagination": {
    "total_count": 150,
    "limit": 20,
    "has_next": true,
    "has_previous": false,
    "next_cursor": "eyJQYXJ0aXRpb25LZXkiOiJkZWZhdWx0IiwiUm93S2V5IjoiZmlsZTEyMyJ9",
    "previous_cursor": null
  }
}
```

**Example:**

```bash
# List all documents
curl -X GET "https://{app}.azurewebsites.net/api/v1/documents?limit=20" \
  -H "Authorization: Bearer {token}" \
  -H "X-Tenant-ID: default"

# Filter by sector and year
curl -X GET "https://{app}.azurewebsites.net/api/v1/documents?sector=TRANSPORT&year_min=2020&year_max=2024&limit=50" \
  -H "Authorization: Bearer {token}" \
  -H "X-Tenant-ID: default"

# Filter by tags and sort by filename
curl -X GET "https://{app}.azurewebsites.net/api/v1/documents?tags=annual,2024&sort_by=filename&sort_order=asc" \
  -H "Authorization: Bearer {token}" \
  -H "X-Tenant-ID: default"
```

---

## Search Endpoints

### Semantic Search

Perform semantic search over document embeddings using natural language queries.

**Endpoint:** `POST /api/v1/search/semantic`

**Request Body:**

```json
{
  "query": "What are the key findings from the 2024 transport sector analysis?",
  "index_name": "embeddings",
  "top_k": 10,
  "min_score": 0.7,
  "file_ids": ["550e8400-e29b-41d4-a716-446655440000"],
  "document_type": "report",
  "tags": ["annual", "2024"],
  "department": "Operations",
  "source": "ezshare",
  "operation_number": "UR-P1180",
  "sector": "TRANSPORT",
  "country": "Uruguay",
  "operation_type": "Loan",
  "dept_id": "INE/TSP",
  "disclosed": true,
  "year": 2024,
  "year_min": 2020,
  "year_max": 2024,
  "document_author": "Jane Doe",
  "file_extension": ".pdf",
  "document_name": "Annual Report 2024",
  "ezshare_id": "EZSHARE-510177122-450",
  "document_publish_date_from": "2024-01-01T00:00:00Z",
  "document_publish_date_to": "2024-12-31T23:59:59Z",
  "filters": {},
  "page_size": 20,
  "page_number": 1,
  "sort_by": "score",
  "order": "desc",
  "include_metadata": true
}
```

**Request Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | Yes | Natural language search query (1-2000 chars) |
| `index_name` | string | No | Target vector index name (default: `embeddings`) |
| `top_k` | integer | No | Number of results (1-100, default: 10) |
| `min_score` | float | No | Minimum relevance score (0.0-1.0, default: 0.0) |
| `file_ids` | array[string] | No | Filter by specific file IDs (max 50, OR logic) |
| `document_type` | string | No | Filter by document type |
| `tags` | array[string] | No | Filter by tags (AND logic - all must match) |
| `department` | string | No | Filter by department |
| `source` | string | No | Filter by source |
| `operation_number` | string | No | Filter by operation number (exact match) |
| `sector` | string or array[string] | No | Filter by sector (exact match or OR logic) |
| `country` | string or array[string] | No | Filter by country (exact match or OR logic) |
| `operation_type` | string | No | Filter by operation type (exact match) |
| `dept_id` | string | No | Filter by department ID (exact match) |
| `disclosed` | boolean | No | Filter by disclosure status |
| `year` | integer | No | Filter by publication year (exact match, 1900-2100) |
| `year_min` | integer | No | Filter by minimum year (1900-2100) |
| `year_max` | integer | No | Filter by maximum year (1900-2100) |
| `document_author` | string | No | Filter by author (partial match) |
| `file_extension` | string | No | Filter by file extension (e.g., .pdf) |
| `document_name` | string | No | Filter by document name (exact match) |
| `ezshare_id` | string | No | Filter by EZSHARE ID (exact match) |
| `document_publish_date_from` | string (ISO) | No | Filter by publish date from |
| `document_publish_date_to` | string (ISO) | No | Filter by publish date to |
| `filters` | object | No | Advanced filters (key/value pairs) |
| `page_size` | integer | No | Page size (1-100). Overrides top_k when provided. |
| `page_number` | integer | No | Page number (1-based). Defaults to 1 when page_size is set. |
| `sort_by` | string | No | Sort field: `score`, `year`, `document_publish_date`, `document_name`, `operation_number`, `country`, `sector`, `document_type`, `department`, `source` |
| `order` | string | No | Sort order: `asc`, `desc` |
| `include_metadata` | boolean | No | Include enriched metadata from FileIndex (default: true) |

**Response:** `200 OK`

```json
{
  "query": "What are the key findings from the 2024 transport sector analysis?",
  "results": [
    {
      "chunk_id": "550e8400-e29b-41d4-a716-446655440000_chunk_5",
      "file_id": "550e8400-e29b-41d4-a716-446655440000",
      "score": 0.89,
      "reranker_score": null,
      "text": "The transport sector analysis for 2024 revealed significant improvements in infrastructure efficiency...",
      "metadata": {
        "filename": "annual-report-2024.pdf",
        "document_name": "Uruguay Transport Sector Annual Report — 2024",
        "page_number": 12,
        "section_path": "Chapter 2 > Results",
        "ezshare_id": "EZS-998877",
        "operation_number": "UR-P1180",
        "document_author": "INE/TSP",
        "country": "Uruguay",
        "sector": "TRANSPORT",
        "dept_id": "INE/TSP",
        "year": 2024
      }
    }
  ],
  "total_results": 8,
  "search_time_ms": 145,
  "embedding_model": "text-embedding-3-small",
  "filters_applied": {
    "sector": "TRANSPORT",
    "year": 2024
  },
  "correlation_id": "abc-123-def"
}
```

**Example:**

```bash
# Basic semantic search
curl -X POST "https://{app}.azurewebsites.net/api/v1/search/semantic" \
  -H "Authorization: Bearer {token}" \
  -H "X-Tenant-ID: default" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "transport infrastructure improvements 2024",
    "top_k": 10,
    "min_score": 0.7
  }'

# Search with filters
curl -X POST "https://{app}.azurewebsites.net/api/v1/search/semantic" \
  -H "Authorization: Bearer {token}" \
  -H "X-Tenant-ID: default" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "infrastructure analysis",
    "sector": "TRANSPORT",
    "country": ["Uruguay", "Argentina"],
    "year_min": 2020,
    "year_max": 2024,
    "disclosed": true,
    "top_k": 20
  }'

# Paginated search with sorting
curl -X POST "https://{app}.azurewebsites.net/api/v1/search/semantic" \
  -H "Authorization: Bearer {token}" \
  -H "X-Tenant-ID: default" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "annual reports",
    "page_size": 25,
    "page_number": 2,
    "sort_by": "year",
    "order": "desc"
  }'
```

**Response Codes:**

- `200` - Search completed successfully
- `400` - Invalid request parameters or unsupported filters
- `404` - Search index not found
- `429` - Rate limit exceeded
- `500` - Internal server error (embedding or search failure)
- `503` - Service not initialized

---

## Collection Management Endpoints

### Create Collection

Create a new vector search collection with specified configuration.

**Endpoint:** `POST /api/v1/collections`

**Request Body:**

```json
{
  "name": "embeddings",
  "vector_dimension": 1536,
  "embedding_model": "text-embedding-3-small",
  "description": "Document embeddings for semantic search"
}
```

**Request Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Collection name (1-100 chars, alphanumeric + `-_`) |
| `vector_dimension` | integer | Yes | Vector dimension size (1-4096, must match model) |
| `embedding_model` | string | Yes | Embedding model name (e.g., `text-embedding-3-small`) |
| `description` | string | No | Optional description (max 500 chars) |

**Response:** `201 Created`

```json
{
  "name": "embeddings",
  "vector_dimension": 1536,
  "embedding_model": "text-embedding-3-small",
  "status": "created",
  "created_at": "2026-01-30T10:00:00Z",
  "correlation_id": "abc-123-def"
}
```

**Example:**

```bash
curl -X POST "https://{app}.azurewebsites.net/api/v1/collections" \
  -H "Authorization: Bearer {token}" \
  -H "X-Tenant-ID: default" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "embeddings",
    "vector_dimension": 1536,
    "embedding_model": "text-embedding-3-small",
    "description": "Main embedding collection"
  }'
```

**Response Codes:**

- `201` - Collection created successfully
- `400` - Invalid request parameters
- `409` - Collection already exists
- `500` - Internal server error
- `503` - Service not initialized

---

### List Collections

List all vector search collections for the tenant.

**Endpoint:** `GET /api/v1/collections`

**Response:** `200 OK`

```json
{
  "collections": [
    {
      "name": "embeddings",
      "vector_dimension": 1536,
      "embedding_model": "text-embedding-3-small",
      "document_count": 1250,
      "created_at": "2026-01-30T10:00:00Z"
    },
    {
      "name": "embeddings-large",
      "vector_dimension": 3072,
      "embedding_model": "text-embedding-3-large",
      "document_count": 500,
      "created_at": "2026-01-28T09:00:00Z"
    }
  ],
  "total_count": 2
}
```

**Example:**

```bash
curl -X GET "https://{app}.azurewebsites.net/api/v1/collections" \
  -H "Authorization: Bearer {token}" \
  -H "X-Tenant-ID: default"
```

---

### Get Collection Details

Get detailed information about a specific collection.

**Endpoint:** `GET /api/v1/collections/{collection_name}`

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `collection_name` | string | Collection name |

**Response:** `200 OK`

```json
{
  "name": "embeddings",
  "vector_dimension": 1536,
  "embedding_model": "text-embedding-3-small",
  "document_count": 1250,
  "index_schema": {
    "fields": [
      "id",
      "chunkId",
      "fileId",
      "content",
      "contentVector",
      "metadata"
    ]
  },
  "created_at": "2026-01-30T10:00:00Z",
  "last_updated": "2026-01-30T12:00:00Z"
}
```

**Example:**

```bash
curl -X GET "https://{app}.azurewebsites.net/api/v1/collections/embeddings" \
  -H "Authorization: Bearer {token}" \
  -H "X-Tenant-ID: default"
```

**Response Codes:**

- `200` - Collection details retrieved
- `404` - Collection not found
- `500` - Internal server error

---

### Delete Collection

Delete a collection and all its documents.

**Warning:** This operation is irreversible. All documents in the collection will be permanently deleted.

**Endpoint:** `DELETE /api/v1/collections/{collection_name}`

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `collection_name` | string | Collection name |

**Response:** `200 OK`

```json
{
  "name": "embeddings",
  "status": "deleted",
  "documents_deleted": 1250,
  "correlation_id": "abc-123-def"
}
```

**Example:**

```bash
curl -X DELETE "https://{app}.azurewebsites.net/api/v1/collections/embeddings" \
  -H "Authorization: Bearer {token}" \
  -H "X-Tenant-ID: default"
```

**Response Codes:**

- `200` - Collection deleted successfully
- `404` - Collection not found
- `500` - Internal server error

---

### Ingest Documents to Collection

Ingest vectorized documents into a collection.

**Endpoint:** `POST /api/v1/collections/{collection_name}/documents`

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `collection_name` | string | Target collection name |

**Request Body:**

```json
{
  "documents": [
    {
      "id": "file123_chunk-0",
      "chunk_id": "chunk-0",
      "file_id": "file123",
      "text": "Document text content...",
      "vector": [0.1, -0.2, 0.3, ...],
      "metadata": {
        "model_version": "text-embedding-3-small",
        "token_count": 128,
        "chunking_strategy": "sentence",
        "chunk_size": 512,
        "overlap_chars": 50
      }
    }
  ]
}
```

**Request Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `documents` | array | Yes | Documents to ingest (1-1000 documents) |
| `documents[].id` | string | Yes | Unique document ID (e.g., file123_chunk-0) |
| `documents[].chunk_id` | string | Yes | Chunk identifier |
| `documents[].file_id` | string | Yes | File identifier |
| `documents[].text` | string | Yes | Document text content (min 1 char) |
| `documents[].vector` | array[float] | Yes | Embedding vector (1-4096 dimensions, must match collection) |
| `documents[].metadata` | object | No | Document metadata |

**Response:** `200 OK`

```json
{
  "collection_name": "embeddings",
  "total_documents": 100,
  "successful": 100,
  "failed": 0,
  "failed_ids": [],
  "processing_time_ms": 150,
  "correlation_id": "abc-123-def"
}
```

**Example:**

```bash
curl -X POST "https://{app}.azurewebsites.net/api/v1/collections/embeddings/documents" \
  -H "Authorization: Bearer {token}" \
  -H "X-Tenant-ID: default" \
  -H "Content-Type: application/json" \
  -d '{
    "documents": [
      {
        "id": "file123_chunk-0",
        "chunk_id": "chunk-0",
        "file_id": "file123",
        "text": "Document content...",
        "vector": [0.1, -0.2, 0.3],
        "metadata": {"token_count": 128}
      }
    ]
  }'
```

**Response Codes:**

- `200` - Documents ingested successfully
- `400` - Invalid request or vector dimension mismatch
- `404` - Collection not found
- `500` - Internal server error

---

## RAG Pipeline Endpoints

These endpoints expose the individual stages of the RAG pipeline for advanced use cases.

### Extract Content from Document

Extract text content from a document using Azure Document Intelligence.

**Endpoint:** `POST /api/v1/contents`

**Request Body:**

```json
{
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "tenant_id": "default",
  "source_container": "raw",
  "output_container": "text"
}
```

**Response:** `202 Accepted`

```json
{
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "markdown_url": "text/550e8400-e29b-41d4-a716-446655440000/text.json",
  "correlation_id": "abc-123-def",
  "processing_time_ms": 1500,
  "created_at": "2026-01-30T10:00:00Z"
}
```

**Example:**

```bash
curl -X POST "https://{app}.azurewebsites.net/api/v1/contents" \
  -H "Authorization: Bearer {token}" \
  -H "X-Tenant-ID: default" \
  -H "Content-Type: application/json" \
  -d '{
    "file_id": "550e8400-e29b-41d4-a716-446655440000",
    "source_container": "raw",
    "output_container": "text"
  }'
```

**Response Codes:**

- `202` - Content extraction started
- `400` - Invalid request or unsupported format
- `404` - Document not found
- `500` - Internal server error

---

### Chunk Document

Chunk a document's extracted text into smaller segments for vectorization.

**Endpoint:** `POST /api/v1/chunks`

**Request Body:**

```json
{
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "tenant_id": "default",
  "source_container": "text",
  "output_container": "chunks",
  "chunking_strategy": {
    "strategy_name": "fixed_size",
    "parameters": {
      "chunk_size": 512,
      "chunk_overlap": 50
    }
  }
}
```

**Supported Chunking Strategies:**

| Strategy | Parameters | Description |
|----------|------------|-------------|
| `fixed_size` | `chunk_size`, `chunk_overlap` | Uniform chunks with configurable size and overlap |
| `semantic_chunking` | `max_chunk_size` | Semantic-aware chunking (future) |
| `markdown_aware` | `max_chunk_size` | Markdown structure-aware chunking (future) |
| `recursive_chunking` | `max_chunk_size`, `min_chunk_size` | Hierarchical chunking (future) |

**Response:** `202 Accepted`

```json
{
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "chunk_count": 25,
  "chunks_url": "chunks/550e8400-e29b-41d4-a716-446655440000/chunks/",
  "chunking_strategy": "fixed_size",
  "correlation_id": "abc-123-def",
  "processing_time_ms": 1250,
  "created_at": "2026-01-30T10:05:00Z"
}
```

**Example:**

```bash
curl -X POST "https://{app}.azurewebsites.net/api/v1/chunks" \
  -H "Authorization: Bearer {token}" \
  -H "X-Tenant-ID: default" \
  -H "Content-Type: application/json" \
  -d '{
    "file_id": "550e8400-e29b-41d4-a716-446655440000",
    "chunking_strategy": {
      "strategy_name": "fixed_size",
      "parameters": {"chunk_size": 512, "chunk_overlap": 50}
    }
  }'
```

**Response Codes:**

- `202` - Document chunking completed
- `400` - Invalid request or unsupported strategy
- `404` - Document or text not found
- `500` - Internal server error

---

### List Chunks

Retrieve a paginated list of chunks filtered by content ID or document ID.

**Endpoint:** `GET /api/v1/chunks`

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `content_id` | string | No | Filter by content ID (same as documentId for now) |
| `document_id` | string | No | Filter by document ID |
| `tenant_id` | string | No | Tenant identifier (default: `default`) |
| `file_version` | integer | No | File version (default: 1) |
| `page_number` | integer | No | Page number, 1-indexed (default: 1) |
| `page_size` | integer | No | Items per page, 1-100 (default: 20) |

**Response:** `200 OK`

```json
{
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "chunk_count": 25,
  "chunks": [
    {
      "chunk_id": "550e8400-e29b-41d4-a716-446655440000_chunk_0",
      "chunk_index": 0,
      "text_preview": "This is the beginning of the document...",
      "char_count": 512,
      "start_char": 0,
      "end_char": 512,
      "page_number": 1
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_pages": 2
  }
}
```

**Example:**

```bash
curl -X GET "https://{app}.azurewebsites.net/api/v1/chunks?document_id=550e8400-e29b-41d4-a716-446655440000&page_size=20" \
  -H "Authorization: Bearer {token}" \
  -H "X-Tenant-ID: default"
```

---

### Vectorize Chunks

Generate vector embeddings for document chunks using Azure OpenAI.

**Endpoint:** `POST /api/v1/embeddings`

**Request Body:**

```json
{
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "tenant_id": "default",
  "file_version": 1,
  "embedding_model": "text-embedding-3-small",
  "batch_size": 50
}
```

**Supported Embedding Models:**

| Model | Dimensions | Description |
|-------|------------|-------------|
| `text-embedding-3-small` | 1536 | Default, cost-effective |
| `text-embedding-3-large` | 3072 | Higher quality, more expensive |

**Response:** `202 Accepted`

```json
{
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "total_chunks": 25,
  "embedded_chunks": 25,
  "failed_chunks": 0,
  "embedding_model": "text-embedding-3-small",
  "embedding_dimension": 1536,
  "embeddings_url": "embeddings/550e8400-e29b-41d4-a716-446655440000/",
  "correlation_id": "abc-123-def",
  "processing_time_ms": 5000,
  "error_message": null,
  "created_at": "2026-01-30T10:10:00Z"
}
```

**Example:**

```bash
curl -X POST "https://{app}.azurewebsites.net/api/v1/embeddings" \
  -H "Authorization: Bearer {token}" \
  -H "X-Tenant-ID: default" \
  -H "Content-Type: application/json" \
  -d '{
    "file_id": "550e8400-e29b-41d4-a716-446655440000",
    "embedding_model": "text-embedding-3-small",
    "batch_size": 50
  }'
```

**Response Codes:**

- `202` - Vectorization completed
- `404` - Document or chunks not found
- `429` - Rate limit exceeded
- `500` - Internal server error

---

## System Information Endpoints

### Get Pipeline Capabilities

Get the capabilities of the RAG pipeline including supported formats, chunking strategies, and embedding models.

**Endpoint:** `GET /api/v1/capabilities`

**Response:** `200 OK`

```json
{
  "supported_formats": [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/png",
    "image/jpeg",
    "image/tiff",
    "image/bmp",
    "text/plain"
  ],
  "chunking_strategies": [
    {
      "name": "fixed_size",
      "parameters": ["chunkSize", "chunkOverlap"]
    },
    {
      "name": "semantic_chunking",
      "parameters": ["maxChunkSize"]
    },
    {
      "name": "markdown_aware",
      "parameters": ["maxChunkSize"]
    },
    {
      "name": "recursive_chunking",
      "parameters": ["maxChunkSize", "minChunkSize"]
    }
  ],
  "embedding_models": [
    {
      "name": "text-embedding-3-small",
      "dimensions": 1536
    },
    {
      "name": "text-embedding-3-large",
      "dimensions": 3072
    }
  ]
}
```

**Example:**

```bash
curl -X GET "https://{app}.azurewebsites.net/api/v1/capabilities" \
  -H "Authorization: Bearer {token}"
```

---

## Error Handling

### Error Response Format

All API errors follow a consistent format:

```json
{
  "error": "ErrorType",
  "message": "Human-readable error message",
  "details": {
    "field": "additional context"
  },
  "correlation_id": "abc-123-def"
}
```

### Common Error Types

| Error Type | HTTP Code | Description |
|------------|-----------|-------------|
| `ValidationError` | 400 | Invalid request parameters |
| `UnsupportedFormatError` | 400 | Document format not supported |
| `InvalidChunkingStrategyError` | 400 | Chunking strategy not supported |
| `UnsupportedFilterError` | 400 | Filter parameters not supported |
| `VectorDimensionMismatchError` | 400 | Vector dimension doesn't match collection |
| `DocumentNotFoundError` | 404 | Document not found in storage |
| `TextNotFoundError` | 404 | Extracted text not found |
| `ChunksNotFoundError` | 404 | Chunks not found for document |
| `IndexNotFoundError` | 404 | Collection/index not found |
| `IndexAlreadyExistsError` | 409 | Collection already exists |
| `RateLimitError` | 429 | API rate limit exceeded |
| `DocumentProcessingError` | 500 | Document processing failed |
| `ChunkingError` | 500 | Chunking operation failed |
| `EmbeddingError` | 500 | Embedding generation failed |
| `VectorDatabaseError` | 500 | Vector database operation failed |
| `InternalServerError` | 500 | Unexpected server error |

### Rate Limiting

When rate limits are exceeded, the API returns:

**Response:** `429 Too Many Requests`

```json
{
  "error": "RateLimitError",
  "message": "API rate limit exceeded",
  "details": {
    "retry_after_seconds": 60
  },
  "correlation_id": "abc-123-def"
}
```

**Headers:**
```
Retry-After: 60
```

### Correlation IDs

All responses include a `correlation_id` field for request tracing and debugging. Include this ID when reporting issues.

---

## Additional Notes

### Pagination Strategies

The API uses two pagination approaches:

1. **Cursor-based pagination** (Document Management):
   - Use `cursor` parameter for next/previous page
   - More efficient for large datasets
   - Cursors are opaque strings, do not parse

2. **Page-based pagination** (RAG Pipeline):
   - Use `page_number` and `page_size` parameters
   - Simpler for predictable datasets

### Filtering Best Practices

1. **Promoted Fields** (server-side filtering in metadata storage):
   - Use for: `operation_number`, `country`, `sector`, `year`, `disclosed`, `operation_type`, `dept_id`, `document_author`, `file_extension`, `access_to_information_policy`, `ezshare_id`
   - More efficient, filters applied at database level

2. **JSON Metadata Fields** (in-memory filtering):
   - Use for: `document_type`, `tags`, `source`, `department`
   - Less efficient, filters applied after retrieval

3. **Performance Tip**: Combine promoted field filters with JSON metadata filters to minimize in-memory filtering overhead.

### Search Performance

- Semantic search queries are vectorized using the collection's embedding model
- Vector search uses Azure AI Search's HNSW algorithm for efficient similarity search
- Apply filters to reduce search space and improve performance
- Use `min_score` to filter low-relevance results
- Consider `top_k` vs `page_size`: `top_k` is for simple result limiting, `page_size` enables pagination

### Best Practices

1. **Document Upload**: Always provide `ezshare_id` for duplicate detection
2. **Metadata**: Use promoted fields for frequently filtered attributes
3. **Search**: Start with broad queries, then refine with filters
4. **Collections**: Use separate collections for different embedding models
5. **Chunking**: Test different chunk sizes for your document types
6. **Error Handling**: Always check `correlation_id` for debugging

---

**End of API Reference**
