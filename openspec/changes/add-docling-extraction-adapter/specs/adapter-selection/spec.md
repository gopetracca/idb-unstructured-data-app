# adapter-selection Delta

## ADDED Requirements

### Requirement: Extraction Adapter Selection Is Strict

The system SHALL resolve the extraction adapter from `EXTRACTION_ADAPTER` by exact match,
and SHALL NOT treat an unrecognised value as a request for any particular engine.

#### Scenario: Exact match required

- **WHEN** `EXTRACTION_ADAPTER` holds a value that is not one of the recognised engines
- **THEN** startup fails with an error naming the setting and its accepted values

#### Scenario: Contrast with chunker selection

- **WHEN** comparing this behaviour with `CHUNKING_ADAPTER`, where any value other than `chonkie` selects LlamaIndex
- **THEN** extraction is deliberately stricter, because a mis-selected extraction engine changes the stored content of every document while a mis-selected chunker only changes chunk boundaries within an engine-agreed text

#### Scenario: Explicit fake still wins

- **WHEN** `DOCUMENT_INTELLIGENCE_USE_FAKE` is true
- **THEN** the fake adapter is used regardless of `EXTRACTION_ADAPTER`, so local development and tests keep one way to switch every adapter off

### Requirement: Docling Adapter Fails Fast On Missing Model Artifacts

The system SHALL verify Docling's model artifacts when the adapter is constructed and a
path for them is configured, and SHALL fail with a message naming that setting.

#### Scenario: A configured artifacts path holds nothing

- **WHEN** the Docling adapter is constructed and `DOCLING_ARTIFACTS_PATH` names a directory that is absent or empty
- **THEN** construction fails with an error naming `DOCLING_ARTIFACTS_PATH` and how to populate it, rather than deferring to a first conversion that would hang on a blocked download

#### Scenario: No path configured

- **WHEN** `DOCLING_ARTIFACTS_PATH` is unset
- **THEN** Docling resolves the artifacts its own way, which is correct on a workstation and is why the setting exists for the environments where it is not

#### Scenario: Failure surfaces at startup

- **WHEN** the configured extraction engine cannot be constructed for any reason
- **THEN** the failure occurs while the process is starting rather than on the first document, so the readiness probe does not report ready on a deployment that cannot extract, and no queue message is dequeued, failed, redelivered and poisoned to discover it

#### Scenario: Both entrypoints check

- **WHEN** the queue-trigger host starts, as well as the HTTP app
- **THEN** the same check runs, because extraction runs in the trigger and a host that cannot extract should not start

#### Scenario: No silent substitution

- **WHEN** the Docling adapter cannot be constructed
- **THEN** no other adapter is substituted, in contrast with the Azure adapter's fallback to a fake, because a deployment that explicitly asked for Docling has not consented to synthetic text

#### Scenario: Engine selected without its dependency

- **WHEN** `EXTRACTION_ADAPTER` is `docling` in an environment where the optional dependency is not installed
- **THEN** startup fails with an error naming the setting and the command that installs the extra, rather than with a bare `ModuleNotFoundError` for a transitive package name

#### Scenario: The deployment image does not yet build the extra

- **WHEN** `EXTRACTION_ADAPTER` is `docling` in the deployment image, which installs no optional extras
- **THEN** the host fails to start with that error, so the engine is unusable-and-loud rather than usable-looking-and-broken, until the image is built with the extra and its model artifacts
