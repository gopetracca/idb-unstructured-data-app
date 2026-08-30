# Tasks

Sequencing note: §0 is a spike whose result decides whether §2 onward is worth doing.
Land `preserve-full-extraction-output` first — it defines the enriched `MarkdownOutput`,
`analysis.json`, and `analysis_blob_ref` that §3 has to fill.

## 0. Measure before committing

- [ ] 0.1 Assemble a fixture corpus under `tests/fixtures/extraction/` from representative
      IADB documents: a text-heavy publication PDF, a table-heavy operational PDF, a
      scanned/OCR PDF, a DOCX, and one document over 100 pages. Record page counts.
- [ ] 0.2 Write `scripts/compare_extraction_adapters.py`: run both engines over the corpus
      and report, per document — wall-clock, peak RSS, page count, table count, character
      count, and a markdown similarity score between the two `extracted_text` outputs.
- [ ] 0.3 Run the harness and record CPU seconds per page and peak RSS per page. These are
      the numbers the Container Apps sizing in §6 depends on.
- [ ] 0.4 Measure the image-size delta with the `docling` extra plus prefetched artifacts.
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
      `conversion_timeout_seconds` (default below the 5-minute queue visibility timeout),
      `max_pages`, `max_concurrent_conversions`, `do_ocr`, `do_table_structure`.
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
- [ ] 2.3 Set `DOCLING_ARTIFACTS_PATH` as `ENV` so it persists into the final image, and
      confirm `HF_HUB_OFFLINE=1` still holds with the artifacts in place.
- [ ] 2.4 Verify the image builds and starts with the extra off — unchanged size, no
      artifacts, no Docling import.

## 3. Adapter and mapper

- [ ] 3.1 `src/infrastructure/docling/adapter.py` implementing `DocumentIntelligencePort`.
      Construct the `DocumentConverter` once with `artifacts_path`; check the artifacts
      exist at construction and raise naming `DOCLING_ARTIFACTS_PATH` if not.
- [ ] 3.2 Run conversion in a thread executor under a semaphore bounded by
      `max_concurrent_conversions`, so the queue batch size cannot saturate the worker.
- [ ] 3.3 Enforce `conversion_timeout_seconds` and fail the stage with reason
      `conversion_timeout`; enforce `max_pages` before conversion starts with reason
      `page_limit_exceeded`.
- [ ] 3.4 `get_supported_formats()` returns Docling's accepted content types, so the
      capabilities and supported-formats endpoints follow the configured engine.
- [ ] 3.5 `src/infrastructure/docling/mapper.py`: `DoclingDocument` → `MarkdownOutput`.
      `export_to_markdown()` for `extracted_text`; items grouped by `prov[0].page_no` for
      per-page text; `TableItem.data.grid` cells → table cells, carrying
      `start/end_row_offset_idx`, `start/end_col_offset_idx`, and the `column_header` /
      `row_header` / `row_section` flags; `PictureItem` → figures; page size → page geometry.
- [ ] 3.6 Map `DocItemLabel` to the paragraph-role vocabulary in an explicit, reviewed
      table — do not rely on the two vocabularies coinciding. Anything unmapped keeps the
      Docling label verbatim rather than being dropped or guessed.
- [ ] 3.7 Convert `prov[].bbox` from Docling's bottom-left origin to the stored contract's
      convention and record the unit. Do not copy coordinates across origins.
- [ ] 3.8 Leave `spans`, `styles`, and `key_value_pairs` empty; do not synthesise markdown
      character offsets. Add a code comment stating why, so it is not "fixed" later.
- [ ] 3.9 Set `extraction_method` to `docling` and, when raw persistence is on, return the
      serialised `DoclingDocument` as the raw payload with
      `analysis_format=docling-document`.
- [ ] 3.10 Map Docling's document-level confidence to `extraction_confidence` where
      available and leave it unset otherwise. Do not derive a per-word-equivalent number.

## 4. Contract changes shared by both engines

- [ ] 4.1 Add `analysis_format` to `ExtractionMetadata`; a missing value reads as Azure
      Document Intelligence output.
- [ ] 4.2 Set `extraction_method` from the adapter that ran rather than from the field's
      default; the Azure adapter keeps its current value.
- [ ] 4.3 In `process_document.py`, write whichever raw payload the adapter returned to
      `analysis.json` and record `analysis_blob_ref`, unchanged apart from being
      engine-agnostic.

## 5. Tests

- [ ] 5.1 `tests/unit/config/test_settings.py` — `EXTRACTION_ADAPTER` default, valid
      values, and startup failure on an unrecognised value.
- [ ] 5.2 `tests/unit/test_container.py` — selection matrix: default, `docling`, explicit
      fake wins, Azure-unconfigured falls back to the fake and not to Docling, `docling`
      without the package raises the stated error.
- [ ] 5.3 `tests/unit/infrastructure/docling/test_mapper.py` — from a fixture
      `DoclingDocument`: tables with a header row and a merged cell survive with correct
      row/column offsets; figures, paragraph roles, page geometry, and bounding regions
      survive; `spans` and `styles` are empty; coordinate origin is converted.
- [ ] 5.4 Table reconstruction test mirroring the Azure one: rebuild the grid from stored
      cells alone and assert it tiles `row_count × column_count` without overlap.
- [ ] 5.5 `tests/unit/infrastructure/docling/test_adapter.py` — artifacts missing raises at
      construction naming `DOCLING_ARTIFACTS_PATH`; conversion timeout fails with
      `conversion_timeout`; over-limit page count fails with `page_limit_exceeded` before
      conversion starts; concurrency is bounded.
- [ ] 5.6 Cross-engine contract test: the same fixture through both adapters produces
      `MarkdownOutput` objects that validate against the same model and agree on page
      count and table count within a stated tolerance.
- [ ] 5.7 Chunking regression: `chunk_document` over a Docling-produced `text.json`
      chunks successfully with no engine-specific handling.
- [ ] 5.8 `tests/unit/presentation/` — capabilities and supported-formats reflect the
      configured engine.
- [ ] 5.9 Mark any test that needs real model artifacts so it skips cleanly when they are
      absent; the default `pytest` run must not require them.

## 6. Docs and spec bookkeeping

- [ ] 6.1 Document `EXTRACTION_ADAPTER`, the `DOCLING_*` settings, and the build arg in
      `docs/`, including the fields Docling cannot fill and why they are empty.
- [ ] 6.2 Record the §0 measurements in `docs/` — throughput, memory, image size, and the
      cost crossover — and derive the Container Apps CPU/memory recommendation from them.
- [ ] 6.3 Document the mixed-corpus story: `extraction_method` and `analysis_format`
      identify the engine, and output predating the field reads as Azure.
- [ ] 6.4 State the page-count ceiling implied by the queue visibility timeout, and that
      raising `visibilityTimeout` is a separate proposal.
- [ ] 6.5 Add `src/infrastructure/docling/**` → `content-extraction` to
      `openspec/coverage.md`.
- [ ] 6.6 Add the ticket row to `openspec/provenance.md` once the Jira key is assigned.
