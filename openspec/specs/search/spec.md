# search Specification

## Purpose

Serve the read side of the RAG system: retrieve the most relevant document chunks for a
natural-language query, in semantic, keyword, or hybrid mode, with metadata filtering,
sorting, pagination, and an optional semantic reranker. Search is split into
document-category-specific endpoints so each exposes only the filters its schema
supports.

## Requirements

### Requirement: Category-Specific Search Endpoints

The system SHALL expose one search endpoint per document category, each hard-coding its
own document category and rejecting filters belonging to another category.

#### Scenario: Operational search

- **WHEN** `POST /api/v1/search/operational` is called with the `Search` permission
- **THEN** the search runs against operational documents, defaults to index `np-d-operational`, and accepts operational filters such as `operation_number`, `sector`, `operation_type`, `dept_id`, and `access_to_information_policy`

#### Scenario: Publication search

- **WHEN** `POST /api/v1/search/publications` is called with the `Search` permission
- **THEN** the search runs against publication documents and accepts publication filters only

#### Scenario: Cross-category filter rejected

- **WHEN** a request to one category's endpoint carries a filter defined only for another category
- **THEN** the request is rejected as a schema error with `422`

#### Scenario: Category cannot be overridden

- **WHEN** a client attempts to set the document category in the request body
- **THEN** the field is not part of the schema and the request is rejected

#### Scenario: Deprecated generic search

- **WHEN** `POST /api/v1/search` is called
- **THEN** the generic search behaviour still applies and the endpoint is marked deprecated in favour of the category-specific ones

### Requirement: Publications Search Feature Flag

The system SHALL keep publication search disabled until publications have been ingested,
returning a clear service-unavailable response rather than empty results.

#### Scenario: Flag off

- **WHEN** `PUBLICATIONS_SEARCH_ENABLED` is false and `POST /api/v1/search/publications` is called
- **THEN** the response is `503 Service Unavailable` explaining the endpoint is not yet enabled

#### Scenario: Flag on

- **WHEN** `PUBLICATIONS_SEARCH_ENABLED` is true
- **THEN** the endpoint serves searches normally

### Requirement: Search Modes

The system SHALL support semantic (vector-only), keyword (BM25-only), and hybrid
(reciprocal rank fusion) retrieval, generating a query embedding only when the mode needs
one.

#### Scenario: Semantic mode

- **WHEN** `search_mode` is `semantic`
- **THEN** the query is embedded and retrieval is by vector similarity alone

#### Scenario: Keyword mode

- **WHEN** `search_mode` is `keyword`
- **THEN** no query embedding is generated and retrieval is by BM25 full-text matching

#### Scenario: Hybrid mode

- **WHEN** `search_mode` is `hybrid`
- **THEN** the query is both embedded and passed as text, and vector and BM25 results are fused

#### Scenario: Mode unspecified

- **WHEN** the request omits `search_mode`
- **THEN** the configured default mode applies (`hybrid` by default)

### Requirement: Query And Result Bounds

The system SHALL bound query length and result counts.

#### Scenario: Query bounds

- **WHEN** a query is supplied
- **THEN** it must be between 1 and 2000 characters

#### Scenario: Result count bounds

- **WHEN** `top_k` is supplied
- **THEN** it must be between 1 and 100, defaulting to 10

#### Scenario: Minimum score bounds

- **WHEN** `min_score` is supplied
- **THEN** it must be between 0.0 and 1.0, defaulting to 0.0

### Requirement: Metadata Filtering

The system SHALL apply metadata filters to retrieval, reject filter names outside the
supported set, and ignore filters whose value is empty.

#### Scenario: Supported filters

- **WHEN** a request carries filters
- **THEN** they must name supported fields such as `file_ids`, `document_type`, `tags`, `department`, `source`, `operation_number`, `sector`, `country`, `operation_type`, `dept_id`, `disclosed`, `year`, `year_min`, `year_max`, `document_author`, `file_extension`, `document_name`, `ezshare_id`, `document_publish_date_from`, and `document_publish_date_to`

#### Scenario: Unsupported filter

- **WHEN** a filter names a field outside the supported set
- **THEN** an unsupported-filter error listing the supported names is raised and the response is `400`

#### Scenario: Empty filter values pruned

- **WHEN** a filter value is null, a blank string, or an empty list
- **THEN** it is dropped before validation rather than narrowing the search

#### Scenario: File id filter bound

- **WHEN** `file_ids` is supplied
- **THEN** at most 50 ids may be listed

#### Scenario: Year bounds

- **WHEN** `year`, `year_min`, or `year_max` is supplied
- **THEN** each must be between 1900 and 2100

#### Scenario: Applied filters echoed

- **WHEN** a search completes
- **THEN** the response reports the filters that were actually applied

### Requirement: Semantic Reranker

The system SHALL support Azure AI Search's semantic L2 reranker as an opt-in per request,
and SHALL refuse the request when the target collection has no reranker configured.

#### Scenario: Reranker requested on a configured collection

- **WHEN** `enable_reranker` is true and the collection has the reranker enabled
- **THEN** results are reranked and the response reports `reranker_enabled` true when reranker scores were returned

#### Scenario: Reranker requested on an unconfigured collection

- **WHEN** `enable_reranker` is true and the collection has no reranker configured
- **THEN** a validation error is raised pointing at `POST /collections/{name}/reranker` and the response is `400`

#### Scenario: Reranker default

- **WHEN** `enable_reranker` is omitted on a category-specific endpoint
- **THEN** it defaults to false

#### Scenario: Reranker score normalisation

- **WHEN** `min_score` is applied and reranking is active
- **THEN** the reranker score (0–4) is normalised to 0–1 before the comparison

### Requirement: Sorting And Pagination

The system SHALL sort results by a supported field and paginate them, bounding the total
depth a caller can reach.

#### Scenario: Default ordering

- **WHEN** no `sort_by` is supplied
- **THEN** results keep the retrieval ranking, ordered by reranker score where present and otherwise by relevance score

#### Scenario: Unsupported sort field

- **WHEN** `sort_by` names a field outside the supported set
- **THEN** a validation error listing the supported sort fields is raised and the response is `400`

#### Scenario: Order without a sort field

- **WHEN** `order` is supplied without `sort_by`
- **THEN** a validation error is raised

#### Scenario: Null values sort last

- **WHEN** results are sorted by a metadata field some results lack
- **THEN** results missing that field sort after those that have it

#### Scenario: Pagination

- **WHEN** `page_size` and/or `page_number` are supplied
- **THEN** `page_size` must be between 1 and 100, `page_number` at least 1, and the requested page is returned

#### Scenario: Pagination depth cap

- **WHEN** `page_size` multiplied by `page_number` exceeds 100 items
- **THEN** a validation error naming the 100-item maximum is raised and the response is `400`

### Requirement: Search Response Contents

The system SHALL return, for each result, the chunk text and score, plus citation
metadata when requested, and SHALL report query-level diagnostics.

#### Scenario: Result payload

- **WHEN** a search succeeds
- **THEN** the response carries the echoed query, the results, `total_results` counted before pagination, `search_time_ms`, the `embedding_model` used, the applied filters, the `search_mode`, `reranker_enabled`, and the correlation id

#### Scenario: Metadata included

- **WHEN** `include_metadata` is true (the default)
- **THEN** each result carries citation metadata such as `filename`, `document_name`, `page_number`, `section_path`, `ezshare_id`, `operation_number`, `document_type`, `document_author`, `country`, `sector`, `dept_id`, and `year`

#### Scenario: Metadata excluded

- **WHEN** `include_metadata` is false
- **THEN** result metadata is omitted from the response

#### Scenario: Publication results lack operational fields

- **WHEN** a publication result is projected
- **THEN** operational-only fields such as `operation_number`, `sector`, and `dept_id` are returned as null rather than causing an error

### Requirement: Collection Metadata Caching

The system SHALL cache each index's embedding model, vector dimension, and reranker state
to avoid a lookup per search, bounding the cache size.

#### Scenario: Cache hit

- **WHEN** a search targets an index whose info is cached
- **THEN** the cached collection info is used without querying the vector database

#### Scenario: Cache eviction

- **WHEN** the cache holds 128 entries and a new index is queried
- **THEN** the oldest entry is evicted

#### Scenario: Cache invalidation

- **WHEN** a collection's configuration changes
- **THEN** its cache entry can be cleared so subsequent searches see the new configuration

### Requirement: Query Vector Dimension Guard

The system SHALL verify that a generated query vector matches the target index's declared
dimension before searching.

#### Scenario: Mismatch between query vector and index

- **WHEN** the embedding model produces a vector whose length differs from the index's `vector_dimension`
- **THEN** a validation error naming both dimensions and the model is raised and the response is `400`

### Requirement: Search Error Mapping

The system SHALL map search failures to stable HTTP responses and SHALL NOT leak internal
detail on unexpected errors.

#### Scenario: Index not found

- **WHEN** the target index does not exist
- **THEN** the response is `404`

#### Scenario: Validation or unsupported filter

- **WHEN** the request fails validation or names an unsupported filter
- **THEN** the response is `400`

#### Scenario: Embedding or vector database failure

- **WHEN** embedding generation or the vector database call fails
- **THEN** the response is `500`

#### Scenario: Unexpected failure

- **WHEN** any other exception escapes
- **THEN** it is logged with the correlation id and the response is a generic `500`
