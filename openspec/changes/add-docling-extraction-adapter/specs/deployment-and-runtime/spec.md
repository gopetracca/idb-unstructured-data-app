# deployment-and-runtime Delta

## MODIFIED Requirements

### Requirement: Offline Safety Inside The VNet

The system SHALL make the runtime free of surprise outbound downloads, because the
deployed environment restricts egress. Every model or tokenizer artifact any adapter needs
SHALL be present in the image, and any adapter that needs one SHALL fail at construction
when it is absent.

#### Scenario: Tokenizer cache warmed at build time

- **WHEN** the image is built
- **THEN** the `cl100k_base` tokenizer cache is populated into a directory that persists into the final image via environment variable

#### Scenario: Model downloads blocked

- **WHEN** the container runs
- **THEN** HuggingFace hub access is disabled by environment variable, so no model download can be attempted at runtime

#### Scenario: Missing cache fails fast

- **WHEN** the tokenizer cache is absent at startup
- **THEN** the chunker fails at construction with an error naming the offline cache requirement, rather than hanging on a blocked network call

#### Scenario: Extraction model artifacts prefetched

- **WHEN** the image is built with the Docling extra enabled
- **THEN** Docling's layout and table-structure model artifacts are downloaded into a fixed path during the build and that path is exposed via `DOCLING_ARTIFACTS_PATH` in the final image

#### Scenario: Prefetch proves itself at build time

- **WHEN** the model artifacts are prefetched during the build
- **THEN** the build verifies they are present and non-empty and fails if they are not, so a failed download cannot surface later as a startup failure in a deployed environment

#### Scenario: Extraction models are pinned

- **WHEN** the same commit is built twice with the Docling extra enabled
- **THEN** the same model artifact versions are downloaded, so the image's extraction behaviour is reproducible

#### Scenario: Missing extraction artifacts fail fast

- **WHEN** Docling is the configured engine and its artifacts are absent at startup
- **THEN** the adapter fails at construction with an error naming `DOCLING_ARTIFACTS_PATH`, rather than hanging on a blocked download inside a queue trigger and being redelivered

## ADDED Requirements

### Requirement: Optional Extraction Dependencies

The system SHALL make the Docling dependency set optional at build time, so deployments
that do not use it do not carry its weight.

#### Scenario: Extra not enabled

- **WHEN** the image is built without the Docling extra
- **THEN** Docling and its inference dependencies are absent, no model artifacts are downloaded, and the image size is unchanged from before this capability existed

#### Scenario: Extra enabled

- **WHEN** the image is built with the Docling extra
- **THEN** the dependencies install from the lockfile with the rest, so the image still matches what CI resolved

#### Scenario: Build configuration reaches the registry-side build

- **WHEN** the image is built server-side by the container registry
- **THEN** the build arguments that select the Docling extra are passed through to it, so the deployed image can be built with the same configuration as a local build

#### Scenario: Engine selected without its dependency

- **WHEN** `EXTRACTION_ADAPTER` is `docling` in an image built without the extra
- **THEN** startup fails with an error stating that the image was built without Docling support, not with an import traceback

### Requirement: Compute Sizing For In-Process Extraction

The system SHALL treat CPU and memory as a capacity constraint when extraction runs
in-process, because the queue host processes messages in batches on a shared worker.

#### Scenario: Concurrency is bounded independently of the queue batch size

- **WHEN** Docling is the configured engine
- **THEN** concurrent conversions are limited by configuration rather than implicitly by the queue batch size, so a full batch cannot saturate the worker's CPU

#### Scenario: Sizing is evidence-based

- **WHEN** the Docling engine is enabled in a deployed environment
- **THEN** the revision's CPU and memory allocation is set from measured per-page CPU time and peak memory on representative documents, and the measurement is recorded in `docs/`
