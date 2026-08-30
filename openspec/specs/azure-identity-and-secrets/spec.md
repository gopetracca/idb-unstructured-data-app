# azure-identity-and-secrets Specification

## Purpose

Reach Azure dependencies without long-lived keys wherever the SDK allows it. Each client
resolves a credential the same way — an explicit key if one is configured, otherwise a
managed or developer identity — so the same image runs locally under a developer login
and in Azure under a user-assigned managed identity with no code change.

## Requirements

### Requirement: Credential Resolution

The system SHALL resolve an Azure credential from configuration, preferring an explicit
API key when present and otherwise falling back to the ambient identity chain.

#### Scenario: API key configured

- **WHEN** an adapter is constructed with a non-empty API key
- **THEN** a key credential is used

#### Scenario: No API key

- **WHEN** no API key is configured
- **THEN** the default credential chain is used, covering managed identity, workload identity, environment credentials, and a developer login

#### Scenario: User-assigned identity pinned

- **WHEN** `AZURE_CLIENT_ID` names a user-assigned managed identity
- **THEN** the default credential is pinned to that identity rather than relying on system-assigned discovery

### Requirement: API Keys Are Optional For Managed-Identity Services

The system SHALL treat Document Intelligence, embeddings, and vector search as
configured once their endpoint is known, so they work under managed identity with no key.

#### Scenario: Endpoint without a key

- **WHEN** `DOCUMENT_INTELLIGENCE_ENDPOINT` or `VECTOR_SEARCH_ENDPOINT` is set and the matching API key is empty
- **THEN** the adapter is considered configured and authenticates with the ambient identity

#### Scenario: Embeddings need a deployment too

- **WHEN** the embedding adapter is evaluated
- **THEN** it is considered configured only when both the endpoint and the deployment name are set

### Requirement: Storage Authentication Mode

The system SHALL select between account-key and identity-based storage access from
configuration, and SHALL treat the presence of an account name as the switch.

#### Scenario: Account name set

- **WHEN** `AZURE_STORAGE_ACCOUNT_NAME` is set
- **THEN** blob and queue clients address `https://{account}.{blob,queue}.core.windows.net` using the default credential, and the connection string is ignored

#### Scenario: Connection string only

- **WHEN** no account name is set
- **THEN** the connection string is used, defaulting to the local Azurite development value

#### Scenario: Local development detection

- **WHEN** no account name is set and the connection string points at the development storage emulator
- **THEN** the storage layer is treated as local development

### Requirement: Secrets Are Not Disclosed At The Error Boundary

The system SHALL keep credential material out of API responses, so a failure in a
dependency cannot leak the configuration used to reach it.

#### Scenario: Storage failure response

- **WHEN** a storage operation fails
- **THEN** the response carries a generic message and names only the operation, never the underlying exception text, connection string, or key

#### Scenario: Readiness failure response

- **WHEN** a readiness check fails
- **THEN** the response names the dependency and the exception type only
