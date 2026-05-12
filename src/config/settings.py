from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class FileUploadSettings(BaseSettings):
    """File upload configuration for document management API."""

    model_config = SettingsConfigDict(
        env_prefix="FILE_UPLOAD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    max_file_size_mb: int = Field(
        default=50,
        description="Maximum file size in megabytes",
    )
    allowed_mime_types: list[str] = Field(
        default=[
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ],
        description="List of allowed MIME types for upload",
    )

    @computed_field
    @property
    def max_file_size_bytes(self) -> int:
        """Get maximum file size in bytes."""
        return self.max_file_size_mb * 1024 * 1024


class ExampleSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EXAMPLE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    client_id: str = "example"


class AzureStorageSettings(BaseSettings):
    """Azure Storage configuration for RAG pipeline."""

    model_config = SettingsConfigDict(
        env_prefix="AZURE_STORAGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Connection string (supports both Azure and Azurite)
    connection_string: str = Field(
        default="UseDevelopmentStorage=true",
        description="Azure Storage connection string or Azurite default",
    )

    # Storage account name used for managed identity auth.
    # When set, clients use DefaultAzureCredential instead of connection_string.
    # Example: "mystorageaccount" -> https://mystorageaccount.{blob,queue}.core.windows.net
    account_name: str = Field(
        default="",
        description="Azure Storage account name for managed identity auth (overrides connection_string)",
    )

    # Blob container names
    container_raw: str = Field(default="raw", description="Container for original files")
    container_text: str = Field(default="text", description="Container for extracted text")
    container_chunks: str = Field(default="chunks", description="Container for chunked segments")
    container_embeddings: str = Field(default="embeddings", description="Container for embeddings")

    # Queue names
    queue_raw_file: str = Field(default="raw-file", description="Queue for file ingestion")
    queue_raw_to_text: str = Field(default="raw-to-text", description="Queue for text processing")
    queue_text_to_chunks: str = Field(
        default="text-to-chunks",
        description="Queue for document chunking",
    )
    queue_chunk_to_vector: str = Field(default="chunk-to-vector", description="Queue for vectorization")
    queue_ingest_to_db: str = Field(default="ingest-to-db", description="Queue for database ingestion")
    queue_delete_file: str = Field(default="delete-file", description="Queue for file deletion")

    @property
    def container_names(self) -> list[str]:
        """Get all container names."""
        return [
            self.container_raw,
            self.container_text,
            self.container_chunks,
            self.container_embeddings,
        ]

    @property
    def queue_names(self) -> list[str]:
        """Get all queue names."""
        return [
            self.queue_raw_file,
            self.queue_raw_to_text,
            self.queue_text_to_chunks,
            self.queue_chunk_to_vector,
            self.queue_ingest_to_db,
            self.queue_delete_file,
        ]

    @property
    def is_local_development(self) -> bool:
        """Check if using Azurite (local development)."""
        if self.account_name:
            return False
        return "UseDevelopmentStorage=true" in self.connection_string or "127.0.0.1:10000" in self.connection_string


class DocumentIntelligenceSettings(BaseSettings):
    """Azure Document Intelligence configuration."""

    model_config = SettingsConfigDict(
        env_prefix="DOCUMENT_INTELLIGENCE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Azure Document Intelligence endpoint and key
    endpoint: str = Field(
        default="",
        description="Azure Document Intelligence endpoint URL",
    )
    api_key: str = Field(
        default="",
        description="Azure Document Intelligence API key",
    )
    api_version: str = Field(
        default="2024-11-30",
        description="API version to use",
    )

    # Use fake implementation for local development
    use_fake: bool = Field(
        default=False,
        description="Use fake implementation instead of Azure (for local dev)",
    )

    # Processing settings
    simulated_delay_seconds: float = Field(
        default=0.5,
        description="Simulated processing delay for fake adapter",
    )

    # Whether to run integration tests that call the real Azure service.
    # Use values like "on"/"1"/"true"/"yes" to enable, or "off"/"0"/"false"/"no" to disable.
    # Default is "off" to avoid running external calls during normal test runs.
    run_tests: str = Field(
        default="off",
        description='Control running of Document Intelligence integration tests ("on"/"off").',
    )

    # Supported formats
    supported_formats: list[str] = Field(
        default=[
            "application/pdf",
            "image/png",
            "image/jpeg",
            "image/jpg",
            "image/tiff",
            "image/bmp",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/plain",
        ],
        description="Supported document MIME types",
    )

    @property
    def is_configured(self) -> bool:
        """Check if endpoint is configured (api_key is optional when using managed identity)."""
        return bool(self.endpoint)

    @property
    def run_tests_enabled(self) -> bool:
        """Interpret `run_tests` setting as boolean.

        Returns True when set to 1/true/yes/on, False when 0/false/no/off or unset.
        """
        val = (self.run_tests or "").strip().lower()
        if not val:
            return False
        if val in ("1", "true", "yes", "on"):
            return True
        if val in ("0", "false", "no", "off"):
            return False
        # Fallback: if the settings string is not recognized, treat as False
        return False


class EmbeddingSettings(BaseSettings):
    """Embedding configuration for vectorization."""

    model_config = SettingsConfigDict(
        env_prefix="EMBEDDING_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Provider configuration
    endpoint: str = Field(
        default="",
        description="Embedding provider endpoint URL",
    )
    api_key: str = Field(
        default="",
        description="API key for embedding provider",
    )
    api_version: str = Field(
        default="2024-02-01",
        description="API version",
    )

    # Model configuration
    default_model: str = Field(
        default="text-embedding-3-small",
        description="Default embedding model to use",
    )
    deployment_name: str = Field(
        default="",
        description="Deployment name for embeddings",
    )

    # Batch configuration
    max_batch_size: int = Field(
        default=100,
        ge=1,
        le=2048,
        description="Maximum number of texts per API call",
    )
    max_tokens_per_batch: int = Field(
        default=8000,
        ge=1000,
        le=8191,
        description="Maximum tokens per batch",
    )

    # Rate limiting and retry configuration
    retry_delay_base: float = Field(
        default=1.0,
        ge=0.1,
        description="Base delay for exponential backoff (seconds)",
    )
    retry_delay_max: float = Field(
        default=60.0,
        ge=1.0,
        description="Maximum retry delay (seconds)",
    )
    max_retries: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of retry attempts",
    )

    # Use fake implementation for local development
    use_fake: bool = Field(
        default=False,
        description="Use fake implementation instead of real API",
    )

    # Integration test control
    run_tests: str = Field(
        default="off",
        description='Control running of embedding integration tests ("on"/"off").',
    )

    @property
    def is_configured(self) -> bool:
        """Check if embedding is configured (api_key is optional when using managed identity)."""
        return bool(self.endpoint and self.deployment_name)

    @property
    def run_tests_enabled(self) -> bool:
        """Interpret `run_tests` setting as boolean."""
        val = (self.run_tests or "").strip().lower()
        if not val:
            return False
        if val in ("1", "true", "yes", "on"):
            return True
        return False


class ChunkingSettings(BaseSettings):
    """Chunking configuration for document processing."""

    model_config = SettingsConfigDict(
        env_prefix="CHUNKING_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Default chunking parameters
    default_strategy: str = Field(
        default="fixed_size",
        description="Default chunking strategy to use",
    )
    default_chunk_size: int = Field(
        default=512,
        ge=50,
        le=4096,
        description="Default chunk size in characters",
    )
    default_chunk_overlap: int = Field(
        default=50,
        ge=0,
        le=500,
        description="Default overlap between chunks in characters",
    )

    # Adapter selection: "llamaindex" or "chonkie"
    adapter: str = Field(
        default="chonkie",
        description="Chunking adapter to use: 'llamaindex' (fixed_size) or 'chonkie' (structure-aware)",
    )

    # Use fake implementation for local development/testing
    use_fake: bool = Field(
        default=False,
        description="Use fake implementation instead of real adapter (for local dev/testing)",
    )

    # Integration test control
    run_tests: str = Field(
        default="off",
        description='Control running of chunking integration tests ("on"/"off").',
    )

    @property
    def run_tests_enabled(self) -> bool:
        """Interpret `run_tests` setting as boolean."""
        val = (self.run_tests or "").strip().lower()
        if not val:
            return False
        if val in ("1", "true", "yes", "on"):
            return True
        if val in ("0", "false", "no", "off"):
            return False
        return False


class VectorSearchSettings(BaseSettings):
    """Azure AI Search configuration for vector search."""

    model_config = SettingsConfigDict(
        env_prefix="VECTOR_SEARCH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Azure AI Search credentials
    endpoint: str = Field(
        default="",
        description="Azure AI Search endpoint URL",
    )
    api_key: str = Field(
        default="",
        description="Azure AI Search API key",
    )
    default_index_name: str = Field(
        default="embeddings",
        description="Default index name for embeddings",
    )

    # HNSW algorithm parameters
    hnsw_m: int = Field(
        default=4,
        ge=4,
        le=10,
        description="Number of bi-directional links in HNSW graph",
    )
    hnsw_ef_construction: int = Field(
        default=400,
        ge=100,
        le=1000,
        description="Size of dynamic candidate list for constructing the graph",
    )
    hnsw_ef_search: int = Field(
        default=500,
        ge=100,
        le=1000,
        description="Size of dynamic candidate list for search",
    )

    # Batch configuration
    batch_size: int = Field(
        default=1000,
        ge=1,
        le=1000,
        description="Maximum number of documents per batch upload",
    )

    # Semantic reranker (L2) configuration
    semantic_configuration_name: str = Field(
        default="default-semantic-config",
        description="Azure AI Search semantic configuration name used by the L2 reranker",
    )
    enable_reranker_default: bool = Field(
        default=True,
        description="Whether the semantic reranker is enabled by default for new search requests",
    )
    default_search_mode: str = Field(
        default="hybrid",
        description="Default search_mode when the request does not specify one (semantic/keyword/hybrid)",
    )

    # Use fake implementation for testing
    use_fake: bool = Field(
        default=False,
        description="Use fake implementation instead of real Azure AI Search",
    )

    # Integration test control
    run_tests: str = Field(
        default="off",
        description='Control running of vector search integration tests ("on"/"off").',
    )

    @property
    def is_configured(self) -> bool:
        """Check if Azure AI Search is configured (api_key is optional when using managed identity)."""
        return bool(self.endpoint)

    @property
    def run_tests_enabled(self) -> bool:
        """Interpret `run_tests` setting as boolean."""
        val = (self.run_tests or "").strip().lower()
        if not val:
            return False
        if val in ("1", "true", "yes", "on"):
            return True
        return False


class SqlServerSettings(BaseSettings):
    """SQL Server configuration for metadata storage."""

    model_config = SettingsConfigDict(
        env_prefix="SQL_SERVER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    enabled: bool = Field(
        default=False,
        description="Enable SQL Server as metadata store (feature flag)",
    )

    database_url: str = Field(
        default="",
        description="SQLAlchemy async database URL (mssql+aioodbc://...)",
    )

    database_url_migrations: str = Field(
        default="",
        description="SQLAlchemy async database URL (mssql+aioodbc://...) for executing migrations",
    )

    database_url_tests: str = Field(
        default="",
        description="SQLAlchemy async database URL (mssql+aioodbc://...) for executing tests",
    )

    pool_size: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Connection pool size",
    )
    max_overflow: int = Field(
        default=10,
        ge=0,
        le=50,
        description="Max connections above pool_size",
    )
    pool_timeout: int = Field(
        default=30,
        ge=5,
        le=120,
        description="Seconds to wait for a connection from the pool",
    )
    echo_sql: bool = Field(
        default=False,
        description="Log all SQL statements (debug only)",
    )

    @property
    def is_configured(self) -> bool:
        """Check if SQL Server connection is configured."""
        return bool(self.database_url)


class EntraIDSettings(BaseSettings):
    """Microsoft Entra ID (Azure AD) authentication settings."""

    model_config = SettingsConfigDict(
        env_prefix="ENTRA_ID_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    enabled: bool = Field(default=False, description="Enable Entra ID authentication")
    tenant_id: str = Field(default="", description="Azure AD tenant GUID")
    client_id: str = Field(default="", description="API app registration client ID")
    audience: str = Field(default="", description="Token audience — defaults to api://{client_id}")
    jwks_cache_ttl_seconds: int = Field(default=3600, description="JWKS cache TTL in seconds")

    @computed_field
    @property
    def issuer(self) -> str:
        """Expected token issuer URL."""
        return f"https://login.microsoftonline.com/{self.tenant_id}/v2.0"

    @computed_field
    @property
    def effective_jwks_uri(self) -> str:
        """Microsoft JWKS endpoint for this tenant."""
        return f"https://login.microsoftonline.com/{self.tenant_id}/discovery/v2.0/keys"

    @computed_field
    @property
    def effective_audience(self) -> str:
        """Resolved audience — explicit override or api://{client_id}."""
        return self.audience or f"api://{self.client_id}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: str = "dev"
    # Client ID of a user-assigned managed identity. Set AZURE_CLIENT_ID in your
    # Container App environment to pin DefaultAzureCredential to a specific identity.
    azure_client_id: str = Field(
        default="",
        description="User-assigned managed identity client ID (AZURE_CLIENT_ID)",
    )
    logging_level: str = "INFO"
    log_format: str = "json"
    ddtrace_log_level: str = "WARNING"
    azure_sdk_log_level: str = "WARNING"
    dd_apm_ignore_resources: str = Field(
        default="",
        description="Comma-separated span names to drop from APM traces (DD_APM_IGNORE_RESOURCES)",
    )

    # Core settings
    example: ExampleSettings = Field(default_factory=ExampleSettings)

    # Azure Storage settings
    azure_storage: AzureStorageSettings = Field(default_factory=AzureStorageSettings)

    # File upload settings
    file_upload: FileUploadSettings = Field(default_factory=FileUploadSettings)

    # Document Intelligence settings
    document_intelligence: DocumentIntelligenceSettings = Field(
        default_factory=DocumentIntelligenceSettings
    )

    # Chunking settings
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)

    # Embedding settings
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)

    # Vector search settings
    vector_search: VectorSearchSettings = Field(default_factory=VectorSearchSettings)

    # SQL Server settings
    sql_server: SqlServerSettings = Field(default_factory=SqlServerSettings)

    # Entra ID authentication settings
    entra_id: EntraIDSettings = Field(default_factory=EntraIDSettings)

    # Feature flags
    publications_search_enabled: bool = Field(
        default=False,
        description="Enable POST /api/v1/search/publications (requires publications to be ingested). "
        "Set PUBLICATIONS_SEARCH_ENABLED=true to activate.",
    )

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment.lower() in ("development", "dev", "local")

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment.lower() in ("production", "prod")


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get application settings (singleton pattern)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Reload settings from environment (useful for testing)."""
    global _settings
    _settings = Settings()
    return _settings



if __name__ == "__main__":
    settings = get_settings()
    print(settings)

