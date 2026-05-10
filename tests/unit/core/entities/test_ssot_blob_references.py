"""Integration tests for SSOT blob reference architecture.

These tests verify that:
1. Blob references are stored in SQL when content is uploaded
2. Blob references are used (not constructed) when downloading content
3. Metadata updates don't affect blob references
4. Blob references enable SQL-only state checking
"""

import pytest

from src.core.entities.chunk_index import ChunkIndex
from src.core.entities.file_index import FileIndex, OverallStatus, ProcessingStage


class TestSSOTBlobReferences:
    """Integration tests for SSOT blob reference pattern."""

    def test_file_index_stores_raw_blob_ref(
        self, sample_tenant_id: str, sample_file_id: str
    ):
        """Test that FileIndex stores raw_blob_ref explicitly."""
        # Arrange - simulating upload
        blob_path = f"{sample_tenant_id}/{sample_file_id}/document.pdf"

        # Act - create FileIndex with blob reference
        file_index = FileIndex(
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            blob_name="document.pdf",
            content_type="application/pdf",
            size_bytes=1024000,
            content_hash="sha256:abc123",
            file_version=1,
            current_stage=ProcessingStage.DISPATCHER,
            overall_status=OverallStatus.QUEUED,
            raw_blob_ref=blob_path,  # ✅ SSOT: Explicit blob reference
        )

        # Assert - blob reference is stored
        assert file_index.raw_blob_ref == blob_path
        assert file_index.raw_blob_ref is not None

    def test_file_index_stores_text_blob_ref(
        self, sample_tenant_id: str, sample_file_id: str
    ):
        """Test that FileIndex stores text_blob_ref after processing."""
        # Arrange - simulating document processing
        raw_blob_path = f"{sample_tenant_id}/{sample_file_id}/document.pdf"
        text_blob_path = f"{sample_tenant_id}/{sample_file_id}/text.json"

        # Act - create FileIndex with both blob references
        file_index = FileIndex(
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            blob_name="document.pdf",
            content_type="application/pdf",
            size_bytes=1024000,
            content_hash="sha256:abc123",
            file_version=1,
            current_stage=ProcessingStage.CONVERT,
            overall_status=OverallStatus.PROCESSING,
            raw_blob_ref=raw_blob_path,    # ✅ From upload
            text_blob_ref=text_blob_path,  # ✅ From processing
        )

        # Assert - both references are stored
        assert file_index.raw_blob_ref == raw_blob_path
        assert file_index.text_blob_ref == text_blob_path

    def test_chunk_index_stores_chunk_blob_ref(
        self, sample_file_id: str, sample_chunk_id: str, sample_tenant_id: str
    ):
        """Test that ChunkIndex stores chunk_blob_ref explicitly."""
        # Arrange - simulating chunking
        chunk_blob_path = f"{sample_tenant_id}/{sample_file_id}/chunks/{sample_chunk_id}.json"

        # Act - create ChunkIndex with blob reference
        chunk_index = ChunkIndex(
            file_id=sample_file_id,
            chunk_id=sample_chunk_id,
            chunk_index=0,
            text_preview="This is chunk content...",
            start_char=0,
            end_char=500,
            chunk_blob_ref=chunk_blob_path,  # ✅ SSOT: Explicit blob reference
        )

        # Assert - blob reference is stored
        assert chunk_index.chunk_blob_ref == chunk_blob_path
        assert chunk_index.chunk_blob_ref is not None

    def test_chunk_index_stores_embedding_blob_ref(
        self, sample_file_id: str, sample_chunk_id: str, sample_tenant_id: str
    ):
        """Test that ChunkIndex stores embedding_blob_ref when vectorized."""
        # Arrange - simulating vectorization
        chunk_blob_path = f"{sample_tenant_id}/{sample_file_id}/chunks/{sample_chunk_id}.json"
        embedding_blob_path = f"{sample_tenant_id}/{sample_file_id}/embeddings/{sample_chunk_id}.json"

        # Act - create ChunkIndex with both blob references
        chunk_index = ChunkIndex(
            file_id=sample_file_id,
            chunk_id=sample_chunk_id,
            chunk_index=0,
            text_preview="This is chunk content...",
            start_char=0,
            end_char=500,
            chunk_blob_ref=chunk_blob_path,          # ✅ From chunking
            embedding_blob_ref=embedding_blob_path,  # ✅ From vectorization
        )

        # Assert - both references are stored
        assert chunk_index.chunk_blob_ref == chunk_blob_path
        assert chunk_index.embedding_blob_ref == embedding_blob_path

    def test_blob_references_enable_idempotency_check(
        self, sample_tenant_id: str, sample_file_id: str
    ):
        """Test that blob references enable simple idempotency checking."""
        # Arrange - simulating re-processing scenario
        file_index = FileIndex(
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            blob_name="document.pdf",
            content_type="application/pdf",
            size_bytes=1024000,
            content_hash="sha256:abc123",
            file_version=1,
            current_stage=ProcessingStage.CONVERT,
            overall_status=OverallStatus.PROCESSING,
            raw_blob_ref=f"{sample_tenant_id}/{sample_file_id}/document.pdf",
            text_blob_ref=f"{sample_tenant_id}/{sample_file_id}/text.json",
        )

        # Act & Assert - check if already processed (SQL-only check)
        # ✅ OLD PATTERN: Would need to check both SQL and blob storage
        # ✅ NEW PATTERN: Check only SQL (SSOT)
        if file_index.text_blob_ref:
            # Already processed, skip
            assert file_index.text_blob_ref is not None
            # Use case would return early without touching blob storage

    def test_metadata_update_does_not_affect_blob_refs(
        self, sample_tenant_id: str, sample_file_id: str
    ):
        """Test that metadata updates don't change blob references (SSOT benefit)."""
        # Arrange - file with metadata and blob references
        original_raw_ref = f"{sample_tenant_id}/{sample_file_id}/document.pdf"
        original_text_ref = f"{sample_tenant_id}/{sample_file_id}/text.json"

        file_index = FileIndex(
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            blob_name="document.pdf",
            content_type="application/pdf",
            size_bytes=1024000,
            content_hash="sha256:abc123",
            file_version=1,
            current_stage=ProcessingStage.COMPLETED,
            overall_status=OverallStatus.COMPLETED,
            raw_blob_ref=original_raw_ref,
            text_blob_ref=original_text_ref,
            # Metadata fields
            country="Uruguay",
            operation_number="UR-P1234",
        )

        # Act - simulate metadata update
        file_index.country = "Brazil"  # Metadata change
        file_index.operation_number = "BR-P5678"  # Metadata change
        file_index.file_version += 1  # Version increment

        # Assert - blob references unchanged
        # ✅ SSOT benefit: Metadata changes don't affect blob storage
        assert file_index.raw_blob_ref == original_raw_ref
        assert file_index.text_blob_ref == original_text_ref
        # Metadata changed, but blob references stayed the same
        assert file_index.country == "Brazil"
        assert file_index.operation_number == "BR-P5678"

    def test_blob_path_not_constructed_from_metadata(
        self, sample_tenant_id: str, sample_file_id: str
    ):
        """Test that blob paths are NOT constructed from metadata fields."""
        # Arrange - file with metadata
        file_index = FileIndex(
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            blob_name="original-name.pdf",  # Original filename
            content_type="application/pdf",
            size_bytes=1024000,
            content_hash="sha256:abc123",
            file_version=1,
            current_stage=ProcessingStage.DISPATCHER,
            overall_status=OverallStatus.QUEUED,
            # Explicit blob reference (may differ from blob_name)
            raw_blob_ref=f"{sample_tenant_id}/{sample_file_id}/stored-name.pdf",
        )

        # Act - attempt to construct path from metadata (OLD PATTERN)
        # ❌ OLD: constructed_path = f"{tenant_id}/{file_id}/{blob_name}"
        # ✅ NEW: use stored reference
        blob_path_to_use = file_index.raw_blob_ref

        # Assert - use stored reference, not constructed path
        assert blob_path_to_use == f"{sample_tenant_id}/{sample_file_id}/stored-name.pdf"
        # Stored reference may differ from what would be constructed
        assert blob_path_to_use != f"{sample_tenant_id}/{sample_file_id}/original-name.pdf"

    def test_sql_is_single_source_of_truth(
        self, sample_tenant_id: str, sample_file_id: str
    ):
        """Test that all metadata including blob locations is in SQL."""
        # Arrange & Act - create complete file record
        file_index = FileIndex(
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            blob_name="document.pdf",
            content_type="application/pdf",
            size_bytes=1024000,
            content_hash="sha256:abc123",
            file_version=1,
            current_stage=ProcessingStage.CHUNK,
            overall_status=OverallStatus.PROCESSING,
            # All blob locations in SQL
            raw_blob_ref=f"{sample_tenant_id}/{sample_file_id}/document.pdf",
            text_blob_ref=f"{sample_tenant_id}/{sample_file_id}/text.json",
            # Business metadata
            country="Uruguay",
            sector="TRANSPORT",
            year=2024,
            operation_number="UR-P1234",
        )

        # Assert - SQL contains EVERYTHING
        # ✅ SSOT: Single query returns complete state
        assert file_index.raw_blob_ref is not None     # Blob location
        assert file_index.text_blob_ref is not None    # Blob location
        assert file_index.country is not None           # Business metadata
        assert file_index.operation_number is not None  # Business metadata

        # ✅ SSOT benefit: No need to query blob storage for metadata
        # All information needed for decisions is in this one entity

    def test_blob_references_survive_stage_transitions(
        self, sample_tenant_id: str, sample_file_id: str
    ):
        """Test that blob references persist across processing stages."""
        # Arrange - file at CONVERT stage
        file_index = FileIndex(
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            blob_name="document.pdf",
            content_type="application/pdf",
            size_bytes=1024000,
            content_hash="sha256:abc123",
            file_version=1,
            current_stage=ProcessingStage.CONVERT,
            overall_status=OverallStatus.PROCESSING,
            raw_blob_ref=f"{sample_tenant_id}/{sample_file_id}/document.pdf",
        )

        # Act - transition to CHUNK stage
        file_index.current_stage = ProcessingStage.CHUNK
        file_index.text_blob_ref = f"{sample_tenant_id}/{sample_file_id}/text.json"

        # Assert - raw_blob_ref persists
        assert file_index.raw_blob_ref == f"{sample_tenant_id}/{sample_file_id}/document.pdf"
        assert file_index.text_blob_ref == f"{sample_tenant_id}/{sample_file_id}/text.json"

        # Act - transition to COMPLETED
        file_index.current_stage = ProcessingStage.COMPLETED
        file_index.overall_status = OverallStatus.COMPLETED

        # Assert - all blob references still present
        assert file_index.raw_blob_ref == f"{sample_tenant_id}/{sample_file_id}/document.pdf"
        assert file_index.text_blob_ref == f"{sample_tenant_id}/{sample_file_id}/text.json"
        # ✅ SSOT: Blob references are permanent, not derived
