# deployment-and-runtime Specification

## Purpose

Ship the service as one container image that runs identically as an Azure Functions host
and as a Container Apps revision, and roll it out in an order that cannot leave the
database behind the code. Covers image composition, offline-safety inside a locked-down
VNet, immutable image tagging, probe configuration, and the migrate-then-deploy gate.

## Requirements

### Requirement: Single Runtime Image

The system SHALL build one multi-stage image containing the application, its locked
dependencies, the SQL Server ODBC driver, and the Datadog init wrapper.

#### Scenario: Base and entrypoint

- **WHEN** the image is built
- **THEN** it is based on the Azure Functions Python runtime and starts the Functions host through the Datadog serverless-init entrypoint

#### Scenario: Locked dependencies

- **WHEN** dependencies are installed
- **THEN** they are installed from the lockfile without development extras, so the image matches what CI resolved

#### Scenario: Database driver present

- **WHEN** the image is built
- **THEN** the Microsoft ODBC Driver 18 is installed, because the async SQL Server driver requires it at runtime

#### Scenario: Build context is pruned

- **WHEN** the application is copied in
- **THEN** the Docker helper directory and any root CA file are removed from the deployed tree

### Requirement: Offline Safety Inside The VNet

The system SHALL make the runtime free of surprise outbound downloads, because the
deployed environment restricts egress.

#### Scenario: Tokenizer cache warmed at build time

- **WHEN** the image is built
- **THEN** the `cl100k_base` tokenizer cache is populated into a directory that persists into the final image via environment variable

#### Scenario: Model downloads blocked

- **WHEN** the container runs
- **THEN** HuggingFace hub access is disabled by environment variable, so no model download can be attempted at runtime

#### Scenario: Missing cache fails fast

- **WHEN** the tokenizer cache is absent at startup
- **THEN** the chunker fails at construction with an error naming the offline cache requirement, rather than hanging on a blocked network call

### Requirement: Optional Corporate Root CA

The system SHALL make trusting the corporate TLS-inspection root an opt-in build
argument, so the same Dockerfile builds inside and outside the corporate network.

#### Scenario: CA installation disabled

- **WHEN** the CA build argument is false, which is the default
- **THEN** the base image certificate bundle is used unchanged and an empty placeholder certificate satisfies the copy step

#### Scenario: CA installation enabled

- **WHEN** the CA build argument is true
- **THEN** the supplied file must be non-empty and contain a certificate, and it is installed into the system trust store

#### Scenario: Server-side builds supported

- **WHEN** the image is built by a registry-side builder
- **THEN** the CA is passed as a plain build argument and file rather than a builder-only secret mount, so registry builds work

### Requirement: Immutable Image Tagging

The system SHALL tag every built image with an immutable commit-derived tag, and add
version tags only for releases.

#### Scenario: Branch build

- **WHEN** a build runs for a commit that is not a version tag
- **THEN** the image is tagged `sha-<short-sha>` and that tag is published as the primary tag for downstream deploys

#### Scenario: Release build

- **WHEN** a build runs for a `v*` tag
- **THEN** the image additionally carries the version tag and `latest`, and the version tag becomes the primary tag

#### Scenario: Deploys reference an immutable tag

- **WHEN** a revision is deployed
- **THEN** it names a specific `sha-` or version tag rather than a moving tag

#### Scenario: Revision suffix derived from the tag

- **WHEN** a revision is created without an explicit suffix
- **THEN** the suffix is derived from the image tag and sanitised, and the deploy fails with an explicit error when the app name leaves no room for a safe suffix

#### Scenario: Registry-side build

- **WHEN** the image is built by the pipeline
- **THEN** the build runs in the container registry, so no local Docker daemon or image push is required from the runner

### Requirement: Container App Probe Configuration

The system SHALL configure liveness, readiness, and startup probes on the Container App
as part of the deployment, pointing at the health endpoints on the ingress port.

#### Scenario: Probe targets

- **WHEN** probes are configured
- **THEN** liveness targets `/health/live` and both readiness and startup target `/health/ready`, on the app's ingress target port

#### Scenario: Probe timings

- **WHEN** probes are configured
- **THEN** each polls every 10 seconds with a 5-second timeout, liveness and readiness tolerate 3 failures, and startup tolerates 30

#### Scenario: Generous startup budget

- **WHEN** the startup threshold is chosen
- **THEN** it allows for a cold start that loads the ODBC driver and the tokenizer cache, so a slow first boot is not mistaken for a failed one

#### Scenario: Single revision per deploy

- **WHEN** an image and its probes are applied
- **THEN** they are applied in one update so exactly one new revision is created

#### Scenario: Probes are applied on request

- **WHEN** the deploy script is invoked with the configure-probes flag, as the delivery pipeline does
- **THEN** the probe configuration is merged into the same update as the image

#### Scenario: Read-only fields are stripped

- **WHEN** the update payload is built from the live app definition
- **THEN** system metadata and read-only properties are dropped, so the update cannot trip over immutable fields

#### Scenario: Ingress required

- **WHEN** the target app exposes no ingress target port
- **THEN** the probe payload build fails with an explicit error rather than producing an unusable configuration

### Requirement: Migrate Before Deploy

The system SHALL apply database migrations before rolling out the revision that depends
on them, using the same image about to be deployed.

#### Scenario: Ordering

- **WHEN** a deploy runs
- **THEN** the migration job runs first and the revision rollout proceeds only when it succeeds

#### Scenario: Same image

- **WHEN** the migration job runs
- **THEN** it uses the image being deployed, so the migration set matches the code

#### Scenario: Not yet provisioned

- **WHEN** the migrations job name is not configured for the environment
- **THEN** the migration step is skipped and the deploy continues, so the pipeline works before the one-time provisioning is done
