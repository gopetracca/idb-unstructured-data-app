# Add Docling as an alternative content-extraction adapter

## Why

Extraction is the only stage that leaves the tenancy boundary for a per-unit-priced
service, and it is the single point at which the whole pipeline is coupled to one vendor.
`AzureDocumentIntelligenceAdapter` is the only real implementation of
`DocumentIntelligencePort`; the only alternative is a fake that fabricates text. That gives
the deployment three problems:

- **Cost scales with pages, unavoidably.** `prebuilt-layout` is billed per page — publicly
  around **$10 per 1,000 pages** at pay-as-you-go S0, with commitment tiers discounting it
  substantially. Reprocessing a corpus — a new chunking strategy, a new index schema, a bug
  in a downstream stage — pays for extraction again every time. (`preserve-full-extraction-output`
  exists precisely because re-extraction is the expensive operation.)
- **Every document is sent to a remote service.** Some corpora cannot leave the network
  boundary on legal or contractual grounds. Today the answer for those is "do not use the
  pipeline", because the only offline adapter is the fake.
- **There is no second opinion.** Extraction quality is unmeasurable in this repo: nothing
  compares one adapter's output against another's, so "the markdown is wrong" has no
  diagnosis path and no fallback.

Docling is a credible open-source alternative: it runs in-process, is MIT-licensed,
produces a `DoclingDocument` with tables, provenance (page number and bounding box per
item), and reading order, and exports markdown. The published technical report measures
**~3.1 s/page end-to-end on x86 CPU** (median ~0.79 s/page, 95th percentile ~16.3 s/page)
with high table-structure accuracy on their benchmark. The cost is compute and image size
rather than per-page billing.

This change does not replace Document Intelligence. It makes extraction genuinely
pluggable and adds a second real adapter, so the choice becomes a deployment decision with
evidence behind it.

## What Changes

- **`EXTRACTION_ADAPTER` setting** (`document_intelligence` by default, or `docling`),
  mirroring the existing `CHUNKING_ADAPTER` pattern. Default behaviour is unchanged; a
  deployment that sets nothing keeps Azure Document Intelligence.
- **New `DoclingExtractionAdapter`** under `src/infrastructure/docling/`, implementing
  `DocumentIntelligencePort` and producing the same `MarkdownOutput` contract — including
  the structured tables, figures, paragraphs, sections, spans, and per-page geometry that
  `preserve-full-extraction-output` added. Docling's `DoclingDocument` carries all of these
  natively; the mapping is a projection, not a reconstruction.
- **Raw-artifact parity.** When raw persistence is on, the adapter writes the serialised
  `DoclingDocument` to `{tenant_id}/{file_id}/analysis.json`. The two adapters produce
  different raw shapes, so `extraction_metadata` gains `analysis_format`
  (`azure-document-intelligence-analyze-result` or `docling-document`) — a reader must
  never have to guess which schema it is holding.
- **Raw-persistence configuration made engine-neutral.** Whether the verbatim analysis is
  stored is a property of the extraction stage, not of Azure, but it is currently spelled
  `DOCUMENT_INTELLIGENCE_PERSIST_RAW_RESULT` and read straight off the Document
  Intelligence settings object. With Docling selected that reads as if it should not
  apply, while in fact it still governs. Introduce an engine-neutral name and keep the
  existing one honoured so deployed configuration does not break.
- **`extraction_method` becomes meaningful.** It already exists and is hard-coded to
  `azure-document-intelligence`; the Docling adapter sets `docling`, so a stored
  `text.json` records which engine produced it. This is the migration story: mixed corpora
  are legible, not ambiguous.
- **Offline model artifacts baked at build time.** The image sets `HF_HUB_OFFLINE=1` and
  the VNet restricts egress (AIA-416). Docling's layout and table-structure models must be
  prefetched into the image with `docling-tools models download` and addressed via
  `DOCLING_ARTIFACTS_PATH`, exactly as the tiktoken cache is warmed today — and the adapter
  must fail at construction with a message naming the missing artifacts rather than hanging
  on a blocked network call. Build-time prefetch is confirmed viable here; what it needs in
  return is pinned model versions, a build step that verifies the download instead of
  assuming it, and build-args plumbing through the ACR server-side build workflow, which
  accepts none today.
- **Terminable conversion.** Extraction runs inside a queue trigger whose messages are
  invisible for five minutes and poisoned after two dequeues. A CPU-bound Docling
  conversion of a long document can exceed that and be silently redelivered while the first
  attempt is still burning CPU. Bounding it needs a mechanism that actually stops the work:
  cancelling an awaitable does not stop a thread, and Docling's own `document_timeout` is
  cooperative. Conversion therefore runs in a **supervised worker subprocess** that the
  parent kills at a hard deadline, behind two cheaper layers — admission control on pages
  and file size, then the cooperative timeout — so a kill is the exception. This constraint
  exists for the Azure adapter too; Docling makes it bind much sooner.
- **Concurrency capped by memory.** Each worker process holds its own copy of the model
  weights, so `max_concurrent_conversions` is set from measured per-worker RSS rather than
  from the queue's `batchSize: 4`.
- **Optional dependency group.** `docling` (and its torch dependency) install under a
  `docling` extra, so deployments that do not use it do not carry the image weight.
- **An offline comparison harness** under `scripts/`, running both adapters over a fixture
  corpus and reporting per-document markdown similarity, table counts, page counts, and
  wall-clock time — so the adapter choice is made against measurements from IADB's own
  documents rather than from a vendor benchmark.

Out of scope: changing the default adapter; runtime shadow-mode / dual extraction;
chunking, vectorization, or search behaviour; GPU inference; Docling's VLM pipelines.

## Impact

- **Affected specs:** `content-extraction` (modified), `adapter-selection` (modified),
  `deployment-and-runtime` (modified)
- **Builds on:** `preserve-full-extraction-output`, now merged (PR #4). It shipped as
  working code, so the contract this change fills is real rather than planned: the enriched
  `MarkdownOutput` with `tables`, `figures`, `paragraphs`, `sections`, `styles`,
  `key_value_pairs`, `content_format`, and `model_id`; `TextSpan` and `BoundingRegion`;
  `analysis.json` and the `analysis_blob_ref` column. Two details of how it landed shape
  this change and are worth stating, because they differ from how that proposal described
  the work:
  - **The port was not widened.** The verbatim payload rides on
    `MarkdownOutput.raw_analysis: dict[str, Any] | None`, declared `exclude=True` so it
    never reaches `text.json`. That is already engine-neutral — the Docling adapter sets
    the field with `DoclingDocument.export_to_dict()` and the use case persists it
    unchanged. No port or use-case signature has to move.
  - **`tests/support/table_reconstruction.assert_cells_tile_grid` takes the domain
    `ExtractedTable`,** not an Azure type, so a Docling-produced table can be held to
    exactly the same reconstruction bar. The cross-engine contract test is close to free.
- **Affected code:**
  - `src/config/settings.py` — `EXTRACTION_ADAPTER`, new `DoclingSettings`
  - `src/container.py` — `_create_document_intelligence_adapter` gains the branch
  - `src/infrastructure/docling/adapter.py`, `mapper.py` — new
  - `src/core/entities/document_analysis.py` — add `analysis_format`; stop defaulting
    `extraction_method` to `azure-document-intelligence` and `api_version` to a Document
    Intelligence version string, since both are now engine-dependent
  - `src/application/use_cases/process_document.py` — `_store_raw_analysis` reads
    `get_settings().document_intelligence.persist_raw_result` directly, so an
    engine-neutral behaviour is gated by a Document-Intelligence-prefixed setting; make
    that selection engine-neutral
  - `Dockerfile` — prefetch and verify model artifacts, `DOCLING_ARTIFACTS_PATH`
  - `.github/workflows/container-build-acr.yml` — build-args plumbing, which it lacks
    entirely today, plus the delivery workflows that call it
  - `pyproject.toml` / `uv.lock` — optional `docling` group
  - `scripts/compare_extraction_adapters.py` — new
  - `openspec/coverage.md` — `src/infrastructure/docling/**` → `content-extraction`
- **Runtime:** Docling shifts extraction from network-bound to CPU-bound, and adds a
  worker subprocess per concurrent conversion, each holding its own model copy. Container
  Apps CPU/memory for the queue-processing revision has to be sized against measured
  per-worker memory and throughput before this is switched on anywhere real. Whether the
  Functions Python worker permits such a subprocess is an assumption the spike checks
  first — the hard deadline has no other mechanism.
- **Image size:** torch plus the model artifacts add substantially to the image — on the
  order of a gigabyte or more. This lands on cold start, on the deploy path, and on ACR
  storage. It must be measured, not assumed, before the extra is enabled in a deployed
  image.
- **No API contract change.** `POST /api/v1/contents` still returns `202` with the same
  body. `GET /api/v1/capabilities` and `GET /documents/supported-formats` already report
  the configured adapter's formats, so they change value, not shape.
