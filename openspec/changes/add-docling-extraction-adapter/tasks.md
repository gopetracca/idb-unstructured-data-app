# Tasks

Scope note: this change makes Docling **selectable and testable locally**. The image,
deployment and hard-termination work is deferred and listed in §6 rather than dropped —
none of it is needed to evaluate the engine, and all of it is needed before the engine is
switched on in a deployed environment.

## 1. Settings and selection

- [x] 1.1 Add `EXTRACTION_ADAPTER`, accepting `document_intelligence` (default) and
      `docling`, validated by exact match with a startup error naming the accepted values
      on anything else.
- [x] 1.2 Add `DoclingSettings` (`DOCLING_` prefix): `artifacts_path`, `do_ocr`,
      `do_table_structure`, `max_pages`, `max_file_size_bytes`,
      `document_timeout_seconds`.
- [x] 1.3 Branch `_create_document_extractor_adapter` in `src/container.py`: explicit fake
      still wins; `docling` selects the Docling adapter; the Azure-unconfigured fallback to
      the fake is unchanged and never selects Docling.
- [x] 1.4 Raise a clear error naming `EXTRACTION_ADAPTER` and the install command when
      `docling` is selected and the package is not installed, rather than letting a bare
      `ModuleNotFoundError` for a transitive package name surface.
- [x] 1.5 Build the configured extraction adapter at startup, from both the HTTP lifespan
      and the queue-trigger host. Every provider is lazy, so without this the first
      *document* is what discovers an engine that cannot be constructed — inside a queue
      trigger, whose message is then redelivered and poisoned.

## 2. Dependency

- [x] 2.1 Add a `docling` optional dependency group to `pyproject.toml`; regenerate
      `uv.lock`.
- [x] 2.2 Keep the default install unchanged: nothing outside `src/infrastructure/docling/`
      and its tests imports Docling, and the container imports the adapter only in the
      branch that selects it.

## 3. Adapter and mapper

- [x] 3.1 `src/infrastructure/docling/adapter.py` implementing `DocumentExtractorPort`.
      Construct the `DocumentConverter` once; a configured `artifacts_path` that holds
      nothing fails at construction with a message naming `DOCLING_ARTIFACTS_PATH`.
- [x] 3.2 Run the conversion on a worker thread so the event loop keeps serving health
      probes. Document plainly that this does **not** make the conversion interruptible —
      the guarantee is deferred to §6.1.
- [x] 3.3 Enforce the limits in layers: file size against the bytes in hand; `max_pages`
      handed to Docling to apply as it opens the document; Docling's own `document_timeout`
      as the cooperative bound.
- [x] 3.4 Treat anything short of `success` — including partial success — as a stage
      failure, so the run publishes nothing and the last complete run stays current.
- [x] 3.5 `get_supported_formats()` returns Docling's accepted content types, so the
      capabilities and supported-formats endpoints follow the configured engine.
- [x] 3.6 `src/infrastructure/docling/mapper.py`: `DoclingDocument` → `MarkdownOutput`,
      **rendering the markdown itself** and recording each element's range as it writes.
      This is the half of the offset invariant the port assigns to an adapter whose
      provider reports no offsets; searching Docling's own export for the text that
      produced it would be guesswork the moment a phrase repeats.
- [x] 3.7 Render tables with Docling's own renderer and partition that string with
      `partition_pipe_table`. Call `TableItem.export_to_markdown()` *without* the document:
      the document-aware overload prepends the caption, and a table whose rendering opened
      with prose would not be a table under any fragment. The caption is a block of its own
      and is rendered where the document puts it.
- [x] 3.8 Map `DocItemLabel` to `BlockKind` in an explicit table rather than by name
      coincidence, and keep Docling's own label on `ContentBlock.role` so nothing is lost
      to the narrowing.
- [x] 3.9 Map Docling's three cell booleans onto `CellRole`, resolving the both-headers
      case to `stub_head`, and derive `header_rows` from the cells.
- [x] 3.10 Record `prov[].bbox` in Docling's own unit and origin rather than converting it,
      ordering `top`/`bottom` within that origin. This reverses the earlier draft: the
      canonical model records the convention precisely so that no adapter converts.
- [x] 3.11 Leave `spans`, `styles`, `key_value_pairs` and `sections` empty, with a comment
      stating why, so it is not "fixed" later.
- [x] 3.12 Set `extraction_method` to `docling`, `api_version` to the Docling version, and
      `analysis_format` to `docling-document`. Set `raw_analysis` to
      `DoclingDocument.export_to_dict()`.
- [x] 3.13 Leave `extraction_confidence` at 0.0. Docling reports a coarse quality *grade*,
      not a probability; mapping one onto the other would produce a number no consumer
      could tell from a measured one.

## 4. Contract changes shared by both engines

- [x] 4.1 Add `analysis_format` to `ExtractionMetadata`; a missing value reads as Azure
      Document Intelligence output.
- [x] 4.2 Introduce `PERSIST_RAW_EXTRACTION` and have `ProcessDocumentUseCase` read it
      instead of `document_intelligence.persist_raw_result`. The legacy name is still
      honoured; the engine-neutral one wins when both are set.
- [x] 4.3 Confirm `process_document.py` needs no other change: `raw_analysis` is already
      engine-neutral, so the run-scoped write, the single-statement publish of
      `text_blob_ref` and `analysis_blob_ref`, and the displaced-output sweep work as-is.
      No engine-specific path is added.

## 5. Tests

- [x] 5.1 `tests/unit/config/test_extraction_settings.py` — `EXTRACTION_ADAPTER` default,
      accepted values, startup failure on anything else, and that the legacy
      `DOCUMENT_INTELLIGENCE_PERSIST_RAW_RESULT` still governs raw persistence.
- [x] 5.2 `tests/unit/test_container.py` — selection matrix: default, `docling`, explicit
      fake wins, Azure-unconfigured falls back to the fake and not to Docling; `docling`
      without the extra names the setting and the install command; and the startup check
      builds the adapter rather than deferring to the first document.
- [x] 5.3 `tests/support/docling_documents.py` — `DoclingDocument` fixtures built by hand,
      so every mapping decision is testable in milliseconds without model weights.
- [x] 5.4 `tests/unit/infrastructure/docling/test_mapper.py` — reading order and rendering;
      blocks resolving against the text; a caption not swallowed into the table; cell roles,
      merged spans and derived header rows; a vertical merge tying its rows; geometry kept
      in Docling's unit and origin; counts and `analysis_format`; and what is deliberately
      left empty.
- [x] 5.5 Table reconstruction: `assert_cells_tile_grid` on a Docling-produced
      `ExtractedTable`, reusing the existing assertion rather than writing a second copy.
      **It holds for the fixtures and the sample PDF and does not hold in general** —
      measured over two real IADB reports, Docling reported 20 overlapping grid positions
      and 362 declared positions covered by no cell, across 44 tables. Its offsets agree
      with its spans, so this is the model's reading of the page rather than a mapping
      error, and the adapter copies it rather than repairing it. Clean tiling is a
      Document Intelligence guarantee, not a cross-engine one; pinned by
      `TestRealTablesAreCopiedNotRepaired`.
- [x] 5.10 Prove the deployed failure mode: with `docling*` blocked at the meta path — an
      image built without the extra — the real `src/main.py` lifespan refuses to start and
      the error names the setting and the remedy. In a subprocess, because patching an
      import in-process tests the container branch and not the entrypoint.
- [x] 5.6 `tests/unit/infrastructure/docling/test_adapter.py` — over-limit file size is
      refused before conversion; the page limit reaches Docling; an unsupported content type
      is refused; partial success and failure fail the stage; a missing artifacts directory
      fails at construction naming `DOCLING_ARTIFACTS_PATH`.
- [x] 5.7 Add `docling` to `ADAPTERS` in `tests/unit/infrastructure/adapters/test_extractor_contract.py`,
      so the new engine inherits the same bar as the two already there.
- [x] 5.8 `tests/integration/infrastructure/test_docling_live.py` — a **real** conversion of
      the sample PDF, asserting the full canonical contract. This is what proves the
      hand-built fixture is not lying about the shape of a real `DoclingDocument`.
- [x] 5.9 Mark that module `requires_docling_models` and skip it cleanly when the artifacts
      are absent; the default `pytest` run must not require them.

## 6. Deferred — required before a deployed rollout

- [ ] 6.1 **Hard termination.** Run the conversion in a supervised worker subprocess the
      parent kills at a deadline derived from the queue visibility timeout minus the
      stage's remaining work. Prove it with a conversion stub that ignores cooperative
      cancellation, asserting the *process* is gone and that a subsequent conversion
      succeeds on the respawned worker. A test that only asserts the coroutine raised would
      pass against the broken thread design.
- [ ] 6.2 Verify the Azure Functions Python worker permits such a subprocess. A negative
      answer invalidates the design, and there is no other mechanism.
- [ ] 6.3 Bound in-flight conversions by a limit sized against measured per-worker RSS —
      each worker holds its own copy of the model weights, so this is a memory limit, not a
      CPU one — and independent of the queue's `batchSize`.
- [ ] 6.4 Log kills distinctly from cooperative timeouts; a rising kill rate means the
      cooperative timeout is mis-tuned or admission control is too loose.
- [ ] 6.5 Install the `docling` extra and prefetch its model artifacts in the Dockerfile
      behind a build arg, with pinned versions, `DOCLING_ARTIFACTS_PATH` as `ENV`, and
      `HF_HUB_OFFLINE=1` still holding. **Until this lands, `EXTRACTION_ADAPTER=docling`
      is not deployable**: the image runs `uv sync --no-dev --locked` with no extras, so
      the host refuses to start (§1.5) rather than serving an engine it does not have.
- [ ] 6.6 Add build-args plumbing to `.github/workflows/container-build-acr.yml`, which
      accepts none today, and pass the arg through the delivery workflows that call it.
- [ ] 6.7 Verify the image builds and starts with the extra off — unchanged size, no
      artifacts, no Docling import.
- [ ] 6.8 `scripts/compare_extraction_adapters.py`: run both engines over a fixture corpus
      and report wall-clock, peak RSS, page count, table count, character count and a
      markdown similarity score, following `scripts/show_extraction_output.py`'s
      conventions.
- [ ] 6.9 Record the measurements in `docs/` — throughput, per-worker memory, image size,
      cold start, the chunk-boundary effect of the markdown-dialect difference, and the
      volume at which Docling is cheaper than IADB's commitment rate — and derive the
      Container Apps sizing from them.
- [ ] 6.10 Document `EXTRACTION_ADAPTER`, `PERSIST_RAW_EXTRACTION` and the `DOCLING_*`
      settings in `docs/`, including the fields Docling cannot fill and why they are empty,
      and the mixed-corpus story that `extraction_method` and `analysis_format` tell.
- [ ] 6.11 Add the ticket row to `openspec/provenance.md` once the Jira key is assigned.
