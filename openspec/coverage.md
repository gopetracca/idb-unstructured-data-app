# Spec coverage map

Which capability governs which part of the tree. The point of this file is to make
"everything is specced" a checkable claim rather than a feeling: if you add a source
directory and cannot name the capability for it, either the spec is missing or the code
is in the wrong place.

Keep it current when adding a capability or a top-level source directory.

## Source tree → capability

| Path | Capability |
| --- | --- |
| `function_app.py` | `pipeline-orchestration` (trigger registration), `observability` (tracer bootstrap), `adapter-selection` (wiring, shutdown) |
| `src/main.py` | `authentication-authorization` (startup guard), `adapter-selection` (lifespan wiring), `edge-protection` (middleware), `health-and-readiness` (root endpoint) |
| `src/container.py` | `adapter-selection` |
| `src/config/settings.py` | Settings are referenced by name from the capability that uses them; `azure-identity-and-secrets` owns the credential and storage-mode settings |
| `src/core/errors.py` | `api-error-contract` |
| `src/core/entities/document.py`, `file_index.py`, `composites.py` | `metadata-persistence` |
| `src/core/entities/pipeline_state.py`, `processing_event.py` | `pipeline-orchestration`, `pipeline-analytics` |
| `src/core/entities/chunk.py`, `chunk_index.py`, `chunk_metadata_index.py` | `document-chunking` |
| `src/core/entities/embedding.py` | `chunk-vectorization` |
| `src/core/entities/vector_document.py` | `vector-ingestion` |
| `src/core/entities/search_result.py` | `search` |
| `src/core/entities/document_analysis.py` | `content-extraction` |
| `src/core/index_schemas/**` | `index-schema-registry` |
| `src/core/value_objects/document_metadata.py` | `index-schema-registry` |
| `src/core/value_objects/chunking_strategy.py` | `document-chunking` |
| `src/core/value_objects/search_mode.py`, `search_result_metadata.py` | `search` |
| `src/core/value_objects/searchable_metadata.py` | `vector-ingestion`, `index-schema-registry` |
| `src/application/ports/**` | `adapter-selection` (the rule that application code depends only on ports). Individual port signatures are implementation detail and are not specced. |
| `src/application/dto/queue_message.py` | `pipeline-orchestration` |
| `src/application/dto/**` (rest) | The capability of the use case they serve |
| `src/application/use_cases/upload_document.py`, `upload_and_enqueue_document.py` | `document-upload` |
| `src/application/use_cases/list_documents.py`, `update_metadata.py`, `delete_document.py` | `document-management` |
| `src/application/use_cases/process_document.py` | `content-extraction` |
| `src/application/use_cases/chunk_document.py`, `list_chunks.py` | `document-chunking` |
| `src/application/use_cases/vectorize_chunks.py` | `chunk-vectorization` |
| `src/application/use_cases/ingest_documents.py` | `vector-ingestion` |
| `src/application/use_cases/search.py`, `semantic_search.py` | `search` (`semantic_search.py` is a backward-compatible re-export) |
| `src/application/use_cases/manage_collection.py` | `collection-management` |
| `src/application/use_cases/*_and_enqueue_*.py` | `pipeline-orchestration` |
| `src/infrastructure/initialization.py` | `pipeline-orchestration` (best-effort provisioning) |
| `src/infrastructure/azure/clients/credentials.py` | `azure-identity-and-secrets` |
| `src/infrastructure/azure/clients/blob_client.py`, `adapters/blob_store_adapter.py` | `blob-artifact-storage` |
| `src/infrastructure/azure/clients/queue_client.py`, `adapters/queue_publisher_azure.py` | `pipeline-orchestration` |
| `src/infrastructure/azure/clients/search_client.py`, `adapters/vector_search_azure.py` | `search`, `collection-management`, `vector-ingestion` |
| `src/infrastructure/azure/adapters/index_schema_mapper.py` | `index-schema-registry` |
| `src/infrastructure/azure/clients/document_intelligence_client.py`, `adapters/document_intelligence_*.py` | `content-extraction`, `adapter-selection` |
| `src/infrastructure/docling/**`, `src/infrastructure/extraction/**` | `content-extraction`, `adapter-selection` |
| `src/infrastructure/azure/adapters/embedding_*.py` | `chunk-vectorization`, `adapter-selection` |
| `src/infrastructure/chonkie/**`, `src/infrastructure/llamaindex/**` | `document-chunking`, `adapter-selection` |
| `src/infrastructure/sqlserver/database.py`, `models/**`, `repositories/**`, `alembic/**`, `run_migrations.py` | `metadata-persistence` |
| `src/presentation/http/auth/**` | `authentication-authorization` |
| `src/presentation/http/tenant.py` | `tenant-resolution` |
| `src/presentation/http/middleware/**` | `edge-protection` |
| `src/presentation/http/exception_handlers.py` | `api-error-contract` |
| `src/presentation/http/routes/**`, `schemas/**` | The capability of the endpoint they expose |
| `src/presentation/queue/**` | `pipeline-orchestration`, `observability` (span helper usage) |
| `src/utils/base_logger.py`, `dd_span.py`, `trace_context.py` | `observability` |
| `Dockerfile`, `.docker/**` | `deployment-and-runtime` |
| `docker-compose.yml` | `local-development` |
| `host.json` | `pipeline-orchestration` (queue host settings) |
| `scripts/acr_build.*`, `deploy_container_app.*`, `run_migrations_job.sh`, `containerapp_probes.py` | `deployment-and-runtime` |
| `scripts/get_dev_token.*` | `local-development` |
| `scripts/show_extraction_output.py` | `content-extraction` (inspection tool for the convert stage's output) |
| `pyproject.toml` (pytest config), `tests/**` | `local-development` |
| `.github/workflows/**` | Not specced — CI/CD wiring is described in the workflows themselves and in `deployment-and-runtime` for what it produces |

## Deliberately not specced

- `__init__.py` files, type aliases, and pure re-exports.
- Port interface signatures. `adapter-selection` specs the architectural rule; the method
  lists are implementation detail that would duplicate the code without adding constraint.
- Log message wording. `observability` specs the record *structure* and what must be
  correlatable, not the prose of individual lines.
- GitHub Actions workflow structure. What a deploy must *do* is in
  `deployment-and-runtime`; which YAML file does it is not a product requirement.
