# Add Docling as an alternative content-extraction adapter

## Why

Extraction is the only stage that leaves the tenancy boundary for a per-unit-priced
service, and it is the single point at which the whole pipeline is coupled to one vendor.
`AzureDocumentIntelligenceAdapter` is the only real implementation of
`DocumentExtractorPort`; the only alternative is a fake that fabricates text. That gives
the deployment three problems:

- **Cost scales with pages, unavoidably.** `prebuilt-layout` is billed per page — publicly
  around **$10 per 1,000 pages** at pay-as-you-go S0, with commitment tiers discounting it
  substantially. Reprocessing a corpus — a new chunking strategy, a new index schema, a bug
  in a downstream stage — pays for extraction again every time.
- **Every document is sent to a remote service.** Some corpora cannot leave the network
  boundary on legal or contractual grounds. Today the answer for those is "do not use the
  pipeline", because the only offline adapter is the fake.
- **There is no second opinion.** Extraction quality is unmeasurable in this repo: nothing
  compares one adapter's output against another's, so "the markdown is wrong" has no
  diagnosis path and no fallback.

Docling is a credible open-source alternative: it runs in-process, is MIT-licensed,
produces a `DoclingDocument` with tables, provenance (page number and bounding box per
item), and reading order, and exports markdown. The cost is compute and image size rather
than per-page billing.

The canonical extraction model that `provider-neutral-extraction-model` shipped (PR #8) is
what makes this a small change rather than a rewrite. It was written with a second engine
in mind and left the pieces this one needs already in place — see **Builds on** below.

This change does not replace Document Intelligence. It makes extraction genuinely
pluggable and adds a second real adapter, so the choice becomes a deployment decision with
evidence behind it.

## What Changes

- **`EXTRACTION_ADAPTER` setting** (`document_intelligence` by default, or `docling`).
  Resolved by exact match, with a startup failure on anything else — deliberately stricter
  than `CHUNKING_ADAPTER`, where any value that is not `chonkie` selects LlamaIndex,
  because a mis-selected extraction engine changes what every document's stored text *is*.
- **New `DoclingExtractionAdapter`** under `src/infrastructure/docling/`, implementing
  `DocumentExtractorPort` and satisfying the same canonical contract as every other
  adapter: blocks that resolve against the extracted text, canonical cell roles, header
  rows derived from cells, and a table rendering partitioned into a prefix, body rows and a
  suffix. It joins the parameterised contract test rather than getting a looser bar of its
  own.
- **The adapter renders the markdown itself.** Docling returns a document tree, not a
  string, so this is the case the port docstring names: nothing hands the adapter offsets,
  and it records the range it wrote for each element as it writes. Table renderings come
  from Docling's own pipe-table renderer and are then *partitioned* by the shared
  `partition_pipe_table` helper — never reassembled from cell spans, which is what makes
  the exactness rule hold by construction.
- **Raw-artifact parity, on the existing publication contract.** `MarkdownOutput.raw_analysis`
  is already an engine-neutral `dict` excluded from serialisation, so the adapter sets it
  to `DoclingDocument.export_to_dict()` and the existing run-scoped write, the
  single-statement publish of `text_blob_ref` and `analysis_blob_ref`, and the sweep of
  what that publish displaced all work unchanged. The two engines produce different raw
  shapes, so `extraction_metadata` gains `analysis_format`
  (`azure-document-intelligence-analyze-result` or `docling-document`) — a reader must
  never have to guess which schema it is holding.
- **Raw-persistence configuration made engine-neutral.** Whether the verbatim analysis is
  stored is a property of the extraction stage, not of Azure, but it is currently spelled
  `DOCUMENT_INTELLIGENCE_PERSIST_RAW_RESULT`. A `PERSIST_RAW_EXTRACTION` setting is
  introduced and wins when set; the existing name is still honoured, so deployed
  configuration does not break.
- **`extraction_method` becomes meaningful.** It already exists and defaults to
  `azure-document-intelligence`; the Docling adapter sets `docling` and reports the Docling
  version as `api_version`, so stored output records which engine produced it. This is the
  migration story: mixed corpora are legible, not ambiguous.
- **Layered limits, honestly labelled.** File size is checked against the bytes in hand;
  the page limit is handed to Docling to apply as it opens the document; Docling's own
  `document_timeout` bounds the conversion. The conversion runs on a worker thread so the
  event loop keeps answering health probes. **That timeout is cooperative, not a
  guarantee** — a conversion inside a single model inference does not check it. Making it a
  guarantee needs a supervised subprocess the parent can kill, which this change
  deliberately does not build; see *Deferred* below.
- **Optional dependency group.** `docling` (and its torch dependency) install under a
  `docling` extra, so deployments that do not use it do not carry the image weight. The
  deployment image builds no extras, so **`EXTRACTION_ADAPTER=docling` is not deployable
  yet** — and rather than let that surface one document at a time inside a queue trigger,
  the configured engine is constructed at startup, from both the HTTP lifespan and the
  queue-trigger host. A host that cannot extract does not start, and the error names the
  setting and the command that installs the extra.

Out of scope: changing the default adapter; runtime shadow-mode / dual extraction;
chunking, vectorization, or search behaviour; GPU inference; Docling's VLM pipelines.

**Deferred, and named so it is not mistaken for done.** Everything below is required
before Docling is switched on in a deployed environment, and none of it is required to
evaluate the engine locally, which is what this change is for:

- **A hard deadline that actually terminates the work** — a supervised worker subprocess
  the parent kills, with a test that proves the process is gone rather than that the
  coroutine returned. Extraction runs in a queue trigger whose messages are invisible for
  five minutes and poisoned after two dequeues, so an overrunning conversion is silently
  redelivered while the first attempt is still burning CPU.
- **Concurrency capped by measured per-worker memory**, since each worker process holds its
  own copy of the model weights.
- **Offline model artifacts baked into the image** — `docling-tools models download` at
  build time, pinned versions, a build step that verifies the download, and build-args
  plumbing through the ACR server-side build workflow, which accepts none today. The
  adapter already fails at construction with a message naming `DOCLING_ARTIFACTS_PATH`
  when a configured path holds nothing, which is the half of this that is code.
- **Measurement** — throughput, per-worker RSS, image-size and cold-start delta, the
  chunk-boundary effect of the markdown-dialect difference, and the volume at which
  Docling's fixed compute cost beats IADB's commitment rate.

## Impact

- **Affected specs:** `content-extraction` (modified), `adapter-selection` (modified)
- **Builds on:** `provider-neutral-extraction-model`, merged as PR #8. It shipped the
  canonical model this adapter fills, and four of its decisions are why this change is
  small:
  - **`ContentBlock` with `(start, end)` into `extracted_text`,** and the offset invariant
    stated on the port as the *adapter's* job — explicitly covering the engine that has to
    render the text itself. That is exactly this adapter.
  - **`partition_pipe_table` in `src/infrastructure/extraction/tables.py`.** Docling
    renders pipe tables; the helper that splits one into a prefix, body rows and a suffix
    already exists and is already used by the fake adapter, so the exactness rule comes
    for free.
  - **`CellRole` and `cell_role_from`.** Docling spells a cell's role as three booleans
    where Document Intelligence spells it as a string; both map onto the canonical role,
    and `header_rows` is derived from the cells rather than assumed.
  - **`BoundingBox` records `unit` and `origin` rather than converting.** Docling reports
    points from a bottom-left origin for a PDF where Document Intelligence reports inches
    from a top-left one. Nothing is converted on the way in — which reverses the earlier
    draft of this change, and is the better answer: a converted number carries a conversion
    no consumer can see.
  - **`tests/support/extractor_contract.py` and the parameterised contract test.** Adding
    an adapter means adding one entry to `ADAPTERS`; the bar is inherited rather than
    rewritten.
- **Affected code:**
  - `src/config/settings.py` — `EXTRACTION_ADAPTER`, `PERSIST_RAW_EXTRACTION`, `DoclingSettings`
  - `src/container.py` — `_create_document_extractor_adapter` gains the branch;
    `verify_extraction_configuration` builds the engine at startup
  - `src/main.py`, `function_app.py` — call that check before serving
  - `src/infrastructure/docling/adapter.py`, `mapper.py` — new
  - `src/core/entities/document_analysis.py` — `analysis_format` on `ExtractionMetadata`
  - `src/application/use_cases/process_document.py` — read the engine-neutral setting
  - `pyproject.toml` / `uv.lock` — optional `docling` extra
  - `tests/support/docling_documents.py` — new; `DoclingDocument` fixtures built by hand
  - `openspec/coverage.md` — `src/infrastructure/docling/**` → `content-extraction`
- **Runtime:** Docling shifts extraction from network-bound to CPU-bound. Container Apps
  CPU/memory has to be sized against measured throughput and memory before this is switched
  on anywhere real — see *Deferred*.
- **Image size:** torch plus the model artifacts add substantially to the image — on the
  order of a gigabyte or more. This lands on cold start, on the deploy path, and on ACR
  storage, which is why the dependency is an extra and the default is unchanged.
- **No API contract change.** `POST /api/v1/contents` still returns `202` with the same
  body. `GET /api/v1/capabilities` and `GET /documents/supported-formats` already report
  the configured adapter's formats, so they change value, not shape.
