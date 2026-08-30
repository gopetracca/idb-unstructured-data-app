# Design

## Context

`DocumentIntelligencePort` has one real implementation and one fake. The port's shape —
bytes plus content type in, `MarkdownOutput` out — is already engine-neutral, so adding a
second engine is a question of whether a second engine can honestly fill that contract,
not of restructuring the layers.

This document is the evaluation that answers it, across the dimensions that decide whether
Docling is usable here: downstream compatibility, extensibility, ease of use, speed, price,
and the operational constraints this specific deployment imposes.

## The comparison

| Dimension | Azure Document Intelligence | Docling |
| --- | --- | --- |
| Execution | Remote HTTPS call, async poller | In-process, CPU-bound (GPU optional, not used here) |
| Billing | Per page (~$10 / 1,000 pages, layout, PAYG S0; commitment tiers lower) | None. Compute and image size instead |
| Data movement | Document bytes leave the VNet | Bytes never leave the container |
| Licence | Commercial service | Open source (MIT); models under their own licences |
| Structured output | `AnalyzeResult`: tables with cell spans, paragraphs with roles, sections, styles, key-value pairs, spans, bounding regions | `DoclingDocument`: tables, text items with `label`, groups, per-item `prov` (page number + bbox), reading order |
| Word-level confidence | Yes, per word | No equivalent |
| Formats | PDF, images, Office, HTML | PDF, images, Office, HTML, MD/TXT, CSV, AsciiDoc, ODF, EPUB, LaTeX, EML, audio/video transcription |
| Scaling | The service's problem | Ours: CPU, memory, and concurrency per replica |
| Failure mode | HTTP error, retryable | Process-local: OOM, timeout, or a bad conversion |
| Cold start | Negligible | Model load on first conversion |

### Downstream compatibility — the deciding question

Everything after extraction reads `text.json`. Concretely:

- `chunk_document` reads exactly one key: `extracted_text`. Nothing else in the pipeline
  reads extraction output today.
- Once `preserve-full-extraction-output` lands, `text.json` also carries pages, tables,
  figures, paragraphs with roles, sections, spans, and bounding regions.

So compatibility reduces to: **can Docling fill the enriched `MarkdownOutput` without
faking anything?** Field by field:

| `MarkdownOutput` field | Docling source | Fidelity |
| --- | --- | --- |
| `extracted_text` | `DoclingDocument.export_to_markdown()` | Direct. Markdown dialect differs from Azure's — same information, different rendering |
| `pages[].page_number` | `PageItem` key | Direct |
| `pages[].text` | items grouped by `prov[0].page_no` | Better than today's Azure mapping, which joins words with spaces and destroys line breaks |
| `pages[].word_count` | derived | Direct |
| `pages[]` geometry (width/height/unit) | `PageItem.size` | Direct; `unit` differs (Docling uses points) |
| `tables` | `TableItem.data` grid: `TableCell` with `start/end_row_offset_idx`, `start/end_col_offset_idx`, and `column_header` / `row_header` / `row_section` flags | Direct, and structurally equivalent to Azure's row/column index + span + `kind` |
| `figures` | `PictureItem` with `prov` | Direct |
| `paragraphs[].role` | `DocItemLabel` (`section_header`, `caption`, `footnote`, `page_header`, `page_footer`, …) | Different vocabulary, same concept — needs an explicit mapping table, not a coincidental one |
| `sections` | group hierarchy / heading levels | Derivable |
| `spans` (offset into the markdown string) | **not native** | Docling anchors items to page coordinates, not to offsets in the exported markdown |
| `bounding_regions` | `prov[].bbox` + `page_no` | Direct, but bottom-left origin vs Azure's top-left — must be normalised, not copied |
| `styles` | no equivalent | Empty |
| `key_value_pairs` | `key_value_region`, `field_key`, `field_value` labels exist, but items are not paired into key→value structures | Empty |
| `extraction_confidence` | no per-word confidence | See below |

Two genuine gaps, and neither is fatal:

**Spans.** Azure gives character offsets into the markdown string, which is how you map a
table back into `extracted_text`. Docling gives page geometry instead. The honest
resolution is to leave `spans` empty for Docling rather than synthesise plausible offsets
— a wrong offset is worse than an absent one, because a consumer cannot tell it is wrong.
Consumers that need spans must check for them; consumers that need geometry get better
data from Docling than from Azure.

**Confidence.** Azure's `extraction_confidence` is an average of per-word OCR confidences.
Docling exposes a document-level confidence grade rather than per-word scores. Mapping a
grade onto the same 0–1 float would make two incomparable numbers look comparable. The
adapter reports Docling's own confidence where available and `analysis_format` says which
engine produced it, so nobody compares the two by accident.

**Conclusion:** the contract holds. The two fields that cannot be filled are declared
empty rather than approximated, and `extraction_method` plus `analysis_format` on every
stored artifact make an adapter's output self-identifying.

### Extensibility

Docling is better here, and it is the strongest argument for the change.

- **Formats.** Docling accepts document types the pipeline currently rejects at upload —
  spreadsheets, presentations, EPUB, AsciiDoc, email, LaTeX, plus audio/video
  transcription. Because `GET /documents/supported-formats` and `/api/v1/capabilities`
  already report *the configured adapter's* list rather than a static one, widening the
  format set is a configuration outcome, not a code change in the presentation layer.
- **Pipeline control.** OCR engine, table-structure mode, image scale, and page ranges are
  all pipeline options. With Azure these are the service's choices.
- **Version pinning.** A pinned Docling version plus pinned model artifacts means the
  extraction behaviour of a given image tag is reproducible. A hosted service can change
  its model under a stable API version, and there is no way to pin against that.
- **Cost of the extensibility:** it is now our job to keep models patched and the image
  reproducible. Azure's version churn is invisible; Docling's is our maintenance.

### Ease of use

Roughly comparable to write, meaningfully harder to operate.

- The adapter itself is small: `DocumentConverter.convert()` plus a mapper. No client
  lifecycle, no credentials, no endpoint configuration, no poller.
- Local development gets genuinely better: a real extractor with no Azure account and no
  secrets, which is what the fake adapter exists to work around today.
- The build gets harder: model artifacts must be prefetched into the image (see below),
  and the image gets large.
- The failure surface moves in-process. Azure failures are HTTP errors with codes.
  Docling failures are OOM, timeout, or a silently poor conversion — the last of which has
  no error at all, which is why the comparison harness is part of this change rather than
  a follow-up.

### Speed

Published Docling numbers on x86 CPU: **~3.1 s/page** end-to-end, median **~0.79 s/page**,
95th percentile **~16.3 s/page** — the spread tracks page complexity, with full-page tables
at the slow end. Azure Document Intelligence is network-bound and its latency is the
service's, not ours, but it is not obviously faster for small documents once the upload and
poll cycle is counted.

The number that matters is not throughput, it is **the five-minute queue visibility
timeout**, with `maxDequeueCount: 2`. At ~3 s/page, roughly 100 pages exhausts the budget.
Past it the message becomes visible again and is reprocessed *while the first attempt is
still running*, then poisoned on the second failure — duplicated CPU on an already
CPU-saturated worker, and no clear error explaining it.

So Docling has to be bounded — and the bound has to be one that actually holds. See
"Decision: conversion runs in a killable process" below, which is where the mechanism is
argued.

**This constraint is not new.** The Azure adapter awaits its poller inside the same trigger
under the same timeout. Docling makes an existing latent bound bind much sooner and much
more visibly. Raising `visibilityTimeout` is a real option but it is a global,
all-stages change to `host.json` — out of scope here, and it should be argued on its own
evidence rather than smuggled in.

### Price

| | Azure DI | Docling |
| --- | --- | --- |
| Marginal cost per page | ~$0.01 at PAYG list (layout) | $0 |
| Fixed cost | none | CPU/memory headroom on the Container Apps revision |
| Reprocessing | full price, every time | free |
| Cost driver | page volume | peak concurrency |

The crossover is a volume question, and the answer depends on IADB's actual commitment-tier
rate, which is not in this repo. The order-of-magnitude shape is what matters: **Docling
converts a per-page variable cost into a fixed compute cost.** For a large one-off backfill
or for repeated reprocessing of a stable corpus it is plainly cheaper. For a low, spiky
volume the always-on CPU headroom is plainly worse. This is exactly why the change ships an
opt-in setting and a measurement harness rather than a migration.

## Decision: a second adapter, not a replacement

Both adapters stay. `EXTRACTION_ADAPTER` selects, defaulting to `document_intelligence`.

Rejected — **replace Document Intelligence.** The two engines are not measured against each
other on IADB documents yet, per-word confidence would be lost outright, and the runtime
consequences (CPU sizing, image size, timeout behaviour) are unproven. Replacing on the
strength of a vendor-published benchmark would be a guess.

Rejected — **runtime shadow mode running both and comparing.** It doubles extraction cost
on every document, including the Azure bill this change exists to reduce, and it puts a
comparison concern inside a pipeline stage. The same evidence comes from an offline harness
over a fixture corpus, at no production cost.

## Decision: follow `CHUNKING_ADAPTER`, including its sharp edge

`EXTRACTION_ADAPTER` mirrors the existing chunker selection, so there is one selection idiom.

It deliberately does **not** copy `CHUNKING_ADAPTER`'s "any value other than `chonkie`
means LlamaIndex" behaviour. A typo in `EXTRACTION_ADAPTER` must fail at startup naming
the valid values. Extraction is the stage where a silent wrong choice is most expensive:
`adapter-selection` already documents that an unconfigured Azure dependency falls back to a
fake that fabricates text and still reports ready. Adding a third selectable adapter to a
lenient matcher widens that hazard. Docling is chosen explicitly or not at all — and it is
never a fallback for an unconfigured Azure endpoint, because "no endpoint configured"
carries no evidence that model artifacts are present.

## Decision: model artifacts are baked at build time and verified at construction

`HF_HUB_OFFLINE=1` and the restricted VNet mean a runtime model download does not fail
fast — it hangs on a blocked connection. The repo has already been through this once with
the chunker's tokenizer (AIA-416), and the resolution there is the precedent:

1. `docling-tools models download` into a fixed path during the image build.
2. `DOCLING_ARTIFACTS_PATH` set as an `ENV` so it persists into the final image, passed to
   `PdfPipelineOptions(artifacts_path=...)`.
3. The adapter checks the path at construction and raises an error naming
   `DOCLING_ARTIFACTS_PATH` if the artifacts are missing.

Point 3 is the one worth insisting on: without it the failure is a hung queue trigger, a
message redelivered to a second hung trigger, and a poison queue entry with no explanation.

Build-time prefetch is confirmed viable in this build environment, which settles the
question of whether Docling can run inside the VNet at all. It carries three requirements
of its own, and they are build-pipeline work, not adapter work:

- **The build agent needs egress the runtime does not have.** Images are built server-side
  by ACR (`container-build-acr.yml`), so the model download happens on the ACR build agent
  rather than on a GitHub runner. That agent must reach the model host, and the corporate
  TLS-inspection root may apply to it exactly as it does to the existing `pip`/`uv` step.
- **Model versions must be pinned.** An unpinned prefetch makes two builds of the same
  commit produce different extraction behaviour, which forfeits the reproducibility that
  is one of the main arguments for Docling over a hosted service in the first place.
- **The build must verify what it downloaded.** If the prefetch silently produces nothing,
  the construction-time check in point 3 turns a build problem into a startup failure in a
  deployed environment. The build should fail on the spot instead. This is the same reason
  the existing tokenizer warm-up runs a real `tiktoken.get_encoding` call rather than just
  creating the cache directory.

`container-build-acr.yml` currently accepts no build arguments at all — the
`INSTALL_IADB_CA` arg exists in the Dockerfile and in `container-docker-build.yml`, but
there is no path for any build arg through the ACR workflow. Plumbing that through is a
prerequisite for enabling the extra in a deployed image.

## Decision: conversion runs in a killable process

A first draft of this change ran conversion in a thread executor and bounded it with
`asyncio.wait_for`. That does not work, and it is worth writing down why, because the
mechanism looks correct and is not.

**Cancelling an awaitable does not stop a thread.** `asyncio.wait_for` around
`run_in_executor` cancels the *await*. The Python thread underneath keeps running
`DocumentConverter.convert()` to completion — there is no mechanism to interrupt a
synchronous CPU-bound call in another thread. The stage would report `conversion_timeout`
while the conversion carried on consuming CPU, and would still be running when the queue
made the message visible again at five minutes and handed a second worker the same
document. The failure this change exists to prevent would remain, now hidden behind a
timeout that appears to handle it.

The same objection disqualifies two other candidates:

- **Docling's own `document_timeout`** is cooperative. It is checked at page and stage
  boundaries, and a document that breaches it comes back as `PARTIAL_SUCCESS`. That makes
  it genuinely useful — it ends the ordinary slow document cheaply and in-process — but it
  cannot interrupt a single long-running model inference, so it cannot be the guarantee.
- **`ProcessPoolExecutor`** does not help by itself either: cancelling a future whose work
  has already started does not terminate the process running it. Process *isolation* is
  necessary; the standard pool's cancellation semantics are not sufficient.

So the guarantee needs a process the supervisor can signal:

Conversion runs in a **supervised worker subprocess**, and at the hard deadline the parent
kills it outright. This is the only layer that actually reclaims the CPU, and it holds
regardless of what the conversion is doing when the deadline arrives.

The worker is **long-lived and reused** rather than spawned per document. Model load is
the dominant fixed cost of a Docling conversion, and paying it per document would eat the
per-page budget. A worker that is killed is respawned, so the kill path costs one model
load, not one per conversion.

### The layers, and what each is for

| Layer | Mechanism | Guarantee |
| --- | --- | --- |
| Admission control | `max_num_pages`, `max_file_size`, `DOCLING_MAX_PAGES` | Refuses work that cannot finish, before spending anything on it |
| Cooperative timeout | Docling `document_timeout` | Ends the ordinary slow document at a checkpoint, cheaply. Bounds overshoot; guarantees nothing |
| Hard deadline | SIGKILL the worker subprocess | Actually stops the work. The guarantee |
| Queue margin | Hard deadline < visibility timeout, less the stage's remaining work | No conversion is running when its own message reappears |

Ordering matters: the cooperative timeout is set *below* the hard deadline, so the normal
slow-document path is a clean in-process failure and the kill is genuinely exceptional. If
kills turn out to be common in practice, that is evidence the cooperative timeout is
mis-tuned or that admission control is too loose — not something to absorb silently.

### What this costs, and where it lands

**Memory multiplies with concurrency.** Each worker process holds its own copy of the
model weights. Two workers is roughly two copies. This is the real cap on
`max_concurrent_conversions` — it is a memory limit, not a CPU limit — and it is why the
concurrency bound is specified against measured per-conversion RSS rather than against the
queue's `batchSize: 4`. §0 has to measure per-worker RSS, not just per-page CPU.

**Subprocess execution must be viable under the Functions Python worker.** This is an
assumption, not a verified fact, and §0 checks it before anything else in the design is
worth building.

**Partial results are discarded.** A conversion cut off by either timeout has produced
some pages. Storing them would put a silently truncated `text.json` into the pipeline and
index a document on incomplete text, with nothing downstream able to tell. The stage fails
instead.

## Decision: `analysis.json` is engine-tagged, never engine-guessed

`preserve-full-extraction-output` stores the raw analysis at
`{tenant_id}/{file_id}/analysis.json`. Docling writes the serialised `DoclingDocument`
there. Two different schemas at one path is acceptable only if the artifact is
self-describing, so `extraction_metadata.analysis_format` and `extraction_method` are
written in `text.json`, and a reader keys off them.

Rejected — **separate paths per engine** (`analysis.docling.json`). Path-by-convention is
against the project's rule that blob references in SQL are the source of truth, and it
would force every reader to probe two paths to find one artifact.

Rejected — **normalise Docling into Azure's `AnalyzeResult` shape.** Fabricating a foreign
schema loses exactly what a verbatim copy exists to preserve, and reintroduces the lossy
filter that `preserve-full-extraction-output` was written to remove.

## Open questions

- IADB's actual Document Intelligence commitment rate, without which the crossover volume
  cannot be computed.
- Whether the Azure Functions Python worker permits long-lived subprocesses. The hard
  deadline has no other mechanism, so a negative answer invalidates the design.
- Measured CPU seconds per page and peak RSS **per worker process** on representative IADB
  documents — decides Container Apps sizing, and the concurrency limit is set by memory
  rather than by CPU.
- Measured image-size delta with the `docling` extra and the prefetched artifacts, and
  whether it should therefore stay opt-in per build or become the default.
- Whether markdown-dialect differences between the two engines materially change chunk
  boundaries for the structure-aware Chonkie chunker. The harness should report it.
