# collection-management Specification

## Purpose

Administer the vector collections (Azure AI Search indexes) that hold document
embeddings: create them with a declared vector dimension, embedding model, and document
category schema; inspect and list them; configure the semantic reranker; and delete them.
The whole surface is administrative.

## Requirements

### Requirement: Create A Collection

The system SHALL create a vector collection with a declared vector dimension, embedding
model, and document category, building the index schema from that category's field
registry.

#### Scenario: Successful creation

- **WHEN** `POST /api/v1/collections` is called with `admin` and a valid body
- **THEN** the index is created with the requested schema and the response is `201` carrying `name`, `vector_dimension`, `embedding_model`, status `created`, `created_at`, and the correlation id

#### Scenario: Name validation

- **WHEN** a collection name is supplied
- **THEN** it must be 1–100 characters matching `^[a-zA-Z0-9-_]+$`

#### Scenario: Vector dimension validation

- **WHEN** `vector_dimension` is supplied
- **THEN** it must be between 1 and 4096

#### Scenario: Document category default

- **WHEN** `document_category` is omitted
- **THEN** it defaults to `operational` and the index carries that category's schema fields

#### Scenario: Collection already exists

- **WHEN** the named collection already exists
- **THEN** the response is `409 Conflict`

#### Scenario: Creation failure

- **WHEN** the vector database rejects the creation
- **THEN** the response is `500`

### Requirement: List Collections

The system SHALL list the available collections with their configuration and document
counts.

#### Scenario: Listing

- **WHEN** `GET /api/v1/collections` is called with `admin`
- **THEN** the response is `200` carrying each collection's `name`, `vector_dimension`, `embedding_model`, `document_count`, and `created_at`, plus a `total_count`

### Requirement: Get Collection Details

The system SHALL return a single collection's configuration, document count, and index
schema.

#### Scenario: Collection exists

- **WHEN** `GET /api/v1/collections/{collection_name}` is called with `admin`
- **THEN** the response is `200` carrying the name, vector dimension, embedding model, document count, index schema, and timestamps

#### Scenario: Collection absent

- **WHEN** the named collection does not exist
- **THEN** the response is `404`

### Requirement: Configure The Semantic Reranker

The system SHALL enable or disable the Azure semantic L2 reranker on a collection and
report the resulting state, so search requests can opt into reranking.

#### Scenario: Enabling the reranker

- **WHEN** `POST /api/v1/collections/{collection_name}/reranker` is called with `admin` and `enabled` true
- **THEN** the semantic configuration is applied to the index and the response is `200` carrying `reranker_enabled` and the `semantic_configuration_name`

#### Scenario: Disabling the reranker

- **WHEN** the same endpoint is called with `enabled` false
- **THEN** the reranker is disabled on the collection and the new state is returned

#### Scenario: Collection absent

- **WHEN** the named collection does not exist
- **THEN** the response is `404`

#### Scenario: Configuration failure

- **WHEN** the vector database rejects the change
- **THEN** the response is `500`

### Requirement: Delete A Collection

The system SHALL delete a collection and every document in it, reporting how many
documents were removed.

#### Scenario: Successful deletion

- **WHEN** `DELETE /api/v1/collections/{collection_name}` is called with `admin`
- **THEN** the index is deleted and the response is `200` carrying status `deleted` and the document count captured before deletion

#### Scenario: Document count unavailable

- **WHEN** the document count cannot be read before deletion
- **THEN** the deletion still proceeds and the reported count is zero

#### Scenario: Collection absent

- **WHEN** the named collection does not exist
- **THEN** the response is `404`

### Requirement: Collections Surface Requires Admin

The system SHALL require the `admin` permission for every collection endpoint, including
reads.

#### Scenario: Non-admin caller

- **WHEN** a caller holding only `documents.read` or `documents.write` invokes any `/api/v1/collections/*` endpoint
- **THEN** the response is `403 Forbidden`
