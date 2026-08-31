# Tasks

Sequencing note: §0 is a spike whose result decides whether §2 onward is worth doing.
> **`provider-neutral-extraction-model` has since shipped (PR #8) and changed the target.**
> Three things these tasks predate: the port is now `DocumentExtractorPort`
> (`DocumentIntelligencePort` remains as an alias, so nothing here fails to compile);
> `MarkdownOutput` gained `blocks`, and cell `kind` became a canonical `role`; and a table
> must carry `rendered` plus a `render_prefix` / `rows` / `render_suffix` partition of it.
> That last one is the part this change's "a projection, not a reconstruction" framing does
> not cover — Docling has no single rendered string to partition, so its adapter must render
> the markdown itself and split what it wrote. The bar is executable:
> `tests/unit/infrastructure/adapters/test_extractor_contract.py` is parameterised over the
> adapters that exist, and a Docling adapter joins that list rather than being measured
> against a looser standard. `src/infrastructure/extraction/tables.py` already has the
> pipe-table partitioner it will need.

`preserve-full-extraction-output` is merged (PR #4), so the `MarkdownOutput`, the
run-scoped analysis sidecar, and `analysis_blob_ref` that §3 fills already exist in code —
along with the atomic publication protocol §3 must not weaken.

## 0. Measure before committing

- [ ] 0.0 Verify the Azure Functions Python worker permits a long-lived subprocess that can
      be signalled and killed from the trigger process. The hard deadline has no other
      mechanism; a negative answer invalidates the design and must be found now, not in
      §3.
- [ ] 0.1 Assemble a fixture corpus under `tests/fixtures/extraction/` from representative
      IADB documents: a text-heavy publication PDF, a table-heavy operational PDF, a
      scanned/OCR PDF, a DOCX, and one document over 100 pages. Record page counts.
- [ ] 0.2 Write `scripts/compare_extraction_adapters.py`, following the conventions of the
      existing `scripts/show_extraction_output.py`: run both engines over the corpus and
      report, per document — wall-clock, peak RSS, page count, table count, character
      count, and a markdown similarity score between the two `extracted_text` outputs.
      Reuse `tests/support/sample_documents.build_sample_pdf` for the bundled default.
- [ ] 0.3 Run the harness and record CPU seconds per page and peak RSS **per worker
      process**, including the model-resident baseline. Concurrency is capped by memory, so
      the per-worker figure — not the per-page one — sets `max_concurrent_conversions` and
      the Container Apps sizing in §6.
- [ ] 0.4 Measure the image-size delta with the `docling` extra plus prefetched artifacts,
      and the cold-start delta it causes. Decide from the numbers whether the extra stays
      opt-in per build or becomes the default.
- [ ] 0.5 Chunk-boundary check: run `chunk_document`'s strategy over both engines'
      `extracted_text` for the same document and report whether the markdown-dialect
      difference materially moves chunk boundaries.
- [ ] 0.6 Get IADB's actual Document Intelligence commitment rate and compute the volume at
      which Docling's fixed compute cost is cheaper. Record it in the design's open
      questions.
- [ ] 0.7 Write the findings into `docs/` and confirm with the team before continuing.

## 1. Settings and selection

- [ ] 1.1 Add `EXTRACTION_ADAPTER` to settings, accepting `document_intelligence` (default)
      and `docling`, validated by exact match with a startup error naming the accepted
      values on anything else.
- [ ] 1.2 Add `DoclingSettings` (`DOCLING_` prefix): `artifacts_path`,
      `document_timeout_seconds` (the engine's cooperative bound), `hard_deadline_seconds`
      (the kill deadline; strictly greater than the cooperative one and strictly less than
      the queue visibility timeout, validated as such), `max_pages`, `max_file_size_bytes`,
      `max_concurrent_conversions`, `do_ocr`, `do_table_structure`.
- [ ] 1.3 Branch `_create_document_intelligence_adapter` in `src/container.py`: explicit
      fake still wins; `docling` selects the Docling adapter; the Azure-unconfigured
      fallback to the fake is unchanged and never selects Docling.
- [ ] 1.4 Raise a clear "image built without Docling support" error when `docling` is
      selected and the package is not installed, rather than letting the ImportError
      surface.

## 2. Dependency and image

- [ ] 2.1 Add a `docling` optional dependency group to `pyproject.toml`; regenerate
      `uv.lock`. Pin Docling and its model-carrying dependencies.
- [ ] 2.2 Add a build arg (default off) that installs the extra and runs
      `docling-tools models download` into a fixed path, mirroring the tiktoken cache
      warming already in the Dockerfile.
- [ ] 2.3 Pin the model artifact versions the prefetch downloads, so two builds of the same
      commit produce the same extraction behaviour.
- [ ] 2.4 Verify the artifacts in the same build step: assert the expected files exist and
      are non-empty, and fail the build if not — as the tokenizer step proves itself by
      running a real `get_encoding` call rather than just creating a directory.
- [ ] 2.5 Set `DOCLING_ARTIFACTS_PATH` as `ENV` so it persists into the final image, and
      confirm `HF_HUB_OFFLINE=1` still holds with the artifacts in place.
- [ ] 2.6 Add build-args plumbing to `.github/workflows/container-build-acr.yml`, which
      accepts none today, and pass the new arg through the delivery workflows that call it.
      Without this the arg cannot reach the ACR server-side build.
- [ ] 2.7 Confirm the ACR build agent can reach the model host, and that the corporate
      TLS-inspection root is handled for it as it already is for the dependency install.
- [ ] 2.8 Verify the image builds and starts with the extra off — unchanged size, no
      artifacts, no Docling import.

## 3. Adapter and mapper

- [ ] 3.1 `src/infrastructure/docling/adapter.py` implementing `DocumentIntelligencePort`.
      Construct the `DocumentConverter` once with `artifacts_path`; check the artifacts
      exist at construction and raise naming `DOCLING_ARTIFACTS_PATH` if not.
- [ ] 3.2 Run conversion in a supervised, long-lived worker **subprocess** with the models
      preloaded, not in a thread executor. At the hard deadline the parent kills the
      process and respawns it. Cancelling the awaitable is not the termination mechanism
      and must not be relied on as one.
- [ ] 3.3 Bound in-flight conversions by `max_concurrent_conversions`, sized against
      measured per-worker RSS — each worker holds its own copy of the model weights, so
      this is a memory limit, not a CPU one — and independent of the queue's `batchSize`.
- [ ] 3.4 Enforce the limits in layers: `max_pages` / max file size before conversion
      starts (`page_limit_exceeded`, `file_size_limit_exceeded`); Docling's own
      `document_timeout` as the cooperative bound; the hard deadline as the guarantee. Set
      `document_timeout` strictly below the hard deadline so a kill is exceptional.
- [ ] 3.5 Derive the hard deadline from the queue visibility timeout minus a margin for the
      stage's remaining work (blob writes, metadata update), so no conversion is running
      when its own message becomes visible again.
- [ ] 3.6 Treat a partial-success conversion as a stage failure so the run publishes
      nothing and the last complete run stays current; never publish truncated text.
- [ ] 3.7 Log kills distinctly from cooperative timeouts. A rising kill rate means the
      cooperative timeout is mis-tuned or admission control is too loose, and that should
      be visible rather than absorbed.
- [ ] 3.8 `get_supported_formats()` returns Docling's accepted content types, so the
      capabilities and supported-formats endpoints follow the configured engine.
- [ ] 3.9 `src/infrastructure/docling/mapper.py`: `DoclingDocument` → `MarkdownOutput`.
      `export_to_markdown()` for `extracted_text`; items grouped by `prov[0].page_no` for
      per-page text; `TableItem.data.grid` cells → table cells, carrying
      `start/end_row_offset_idx`, `start/end_col_offset_idx`, and the `column_header` /
      `row_header` / `row_section` flags; `PictureItem` → figures; page size → page geometry.
- [ ] 3.10 Map `DocItemLabel` to the paragraph-role vocabulary in an explicit, reviewed
      table — do not rely on the two vocabularies coinciding. Anything unmapped keeps the
      Docling label verbatim rather than being dropped or guessed.
- [ ] 3.11 Convert `prov[].bbox` from Docling's bottom-left origin to the stored contract's
      convention and record the unit. Do not copy coordinates across origins.
- [ ] 3.12 Leave `spans`, `styles`, and `key_value_pairs` empty; do not synthesise markdown
      character offsets. Add a code comment stating why, so it is not "fixed" later.
- [ ] 3.13 Set `extraction_method` to `docling`, `api_version` to the Docling version, and
      `analysis_format` to `docling-document`. Set `MarkdownOutput.raw_analysis` to
      `DoclingDocument.export_to_dict()` — the field is a plain dict excluded from
      serialisation, so the existing `_store_raw_analysis` path persists it with no change
      to the port or the use case.
- [ ] 3.14 Map Docling's document-level confidence to `extraction_confidence` where
      available and leave it unset otherwise. Do not derive a per-word-equivalent number.

## 4. Contract changes shared by both engines

- [ ] 4.1 Add `analysis_format` to `ExtractionMetadata`; a missing value reads as Azure
      Document Intelligence output.
- [ ] 4.2 Set `extraction_method` from the adapter that ran rather than from the field's
      default; the Azure adapter keeps its current value.
- [ ] 4.3 Stop defaulting `api_version` to a Document Intelligence version string; each
      adapter sets the version of the engine that ran.
- [ ] 4.4 Introduce an engine-neutral setting for raw-analysis persistence and have
      `_store_raw_analysis` read it instead of
      `get_settings().document_intelligence.persist_raw_result`. Keep
      `DOCUMENT_INTELLIGENCE_PERSIST_RAW_RESULT` honoured, since it is presumably already
      set in deployed configuration, and document which wins if both are set.
- [ ] 4.5 Confirm `process_document.py` needs no other change: `raw_analysis` is already
      engine-neutral, so the run-scoped write, the single-statement publish of
      `text_blob_ref` and `analysis_blob_ref`, and the displaced-output sweep all work
      as-is. Add no engine-specific path — a fixed `analysis.json` would reintroduce the
      overwrite race this protocol exists to prevent.

## 5. Tests

- [ ] 5.1 `tests/unit/config/test_settings.py` — `EXTRACTION_ADAPTER` default, valid
      values, startup failure on an unrecognised value, and that the legacy
      `DOCUMENT_INTELLIGENCE_PERSIST_RAW_RESULT` still governs raw persistence.
- [ ] 5.2 `tests/unit/test_container.py` — selection matrix: default, `docling`, explicit
      fake wins, Azure-unconfigured falls back to the fake and not to Docling, `docling`
      without the package raises the stated error.
- [ ] 5.3 `tests/unit/infrastructure/docling/test_mapper.py` — from a fixture
      `DoclingDocument`: tables with a header row and a merged cell survive with correct
      row/column offsets; figures, paragraph roles, page geometry, and bounding regions
      survive; `spans` and `styles` are empty; coordinate origin is converted.
- [ ] 5.4 Table reconstruction: call the existing
      `tests/support/table_reconstruction.assert_cells_tile_grid` on a Docling-produced
      `ExtractedTable`. It takes the domain type and names no Azure type, so both engines
      are held to one bar — do not write a second copy of the assertion.
- [ ] 5.5 `tests/unit/infrastructure/docling/test_adapter.py` — artifacts missing raises at
      construction naming `DOCLING_ARTIFACTS_PATH`; over-limit page count and file size
      fail before conversion starts; a partial-success result fails the stage rather than
      storing truncated text; concurrency is bounded.
- [ ] 5.6 **Termination test — the one that proves the guarantee.** Give the worker a
      conversion stub that ignores cooperative cancellation entirely (a tight CPU loop).
      Assert the worker process is gone within the hard deadline by checking the process
      itself — not merely that the awaiting call returned — and that a subsequent
      conversion succeeds on the respawned worker. A test that only asserts the coroutine
      raised would pass against the broken thread-executor design and is not sufficient.
- [ ] 5.7 Assert the hard deadline is derived to leave margin inside the queue visibility
      timeout, covering the post-conversion work too — the two run-scoped writes, the
      reference publish, and the sweep — so the arithmetic cannot silently drift if
      `host.json` changes.
- [ ] 5.8 Publication contract, with Docling configured: outputs land under run-scoped
      paths; both references publish in one update; a terminated or failed run publishes
      nothing and discards only its own writes, leaving the previous run's pair referenced
      and intact. Mirror the existing coverage rather than inventing a parallel one — see
      `tests/unit/application/use_cases/test_process_document.py`.
- [ ] 5.9 Two overlapping Docling extractions of one document leave exactly one complete,
      internally consistent pair referenced, and no unreachable blobs.
- [ ] 5.10 Assert a worker killed mid-conversion, or dying of memory exhaustion, leaves the
      parent able to serve health probes and process the next message.
- [ ] 5.11 Cross-engine contract test over `tests/support/sample_documents.build_sample_pdf`
      — the document that already exercises a merged-header table: both adapters produce
      `MarkdownOutput` objects that validate against the same model, both pass
      `assert_cells_tile_grid`, and they agree on page and table count within a stated
      tolerance.
- [ ] 5.12 Chunking regression: `chunk_document` over a Docling-produced text output,
      located through `text_blob_ref`, chunks successfully with no engine-specific
      handling.
- [ ] 5.13 `tests/unit/presentation/` — capabilities and supported-formats reflect the
      configured engine.
- [ ] 5.14 Mark any test that needs real model artifacts so it skips cleanly when they are
      absent; the default `pytest` run must not require them.

## 6. Docs and spec bookkeeping

- [ ] 6.1 Document `EXTRACTION_ADAPTER`, the `DOCLING_*` settings, and the build arg in
      `docs/`, including the fields Docling cannot fill and why they are empty.
- [ ] 6.2 Record the §0 measurements in `docs/` — throughput, memory, image size, and the
      cost crossover — and derive the Container Apps CPU/memory recommendation from them.
- [ ] 6.3 Document the mixed-corpus story: `extraction_method` and `analysis_format`
      identify the engine, and output predating the field reads as Azure.
- [ ] 6.4 State the page-count ceiling implied by the queue visibility timeout, the layered
      limits and which one is the actual guarantee, and that raising `visibilityTimeout` is
      a separate proposal.
- [ ] 6.5 Add `src/infrastructure/docling/**` → `content-extraction` to
      `openspec/coverage.md`.
- [ ] 6.6 Add the ticket row to `openspec/provenance.md` once the Jira key is assigned.
