"""Unit tests for FileIndex entity."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.core.entities.file_index import FileIndex, OverallStatus, ProcessingStage


@pytest.mark.unit
class TestFileIndex:
    """Tests for FileIndex entity."""

    def test_create_file_index_minimal(self) -> None:
        """Test creating FileIndex with minimal required fields."""
        file_index = FileIndex(
            tenant_id="tenant-001",
            file_id="file-001",
            blob_name="document.pdf",
        )

        assert file_index.tenant_id == "tenant-001"
        assert file_index.file_id == "file-001"
        assert file_index.blob_name == "document.pdf"
        assert file_index.collection_name is None
        assert file_index.current_stage == ProcessingStage.DISPATCHER
        assert file_index.overall_status == OverallStatus.QUEUED

    def test_create_file_index_full(self, sample_file_index: FileIndex) -> None:
        """Test creating FileIndex with all fields."""
        assert sample_file_index.content_type == "application/pdf"
        assert sample_file_index.size_bytes == 1024000
        assert sample_file_index.file_version == 1

    def test_mark_processing(self, sample_file_index: FileIndex) -> None:
        """Test marking file as processing."""
        original_updated = sample_file_index.last_updated
        sample_file_index.mark_processing(ProcessingStage.CONVERT)

        assert sample_file_index.current_stage == ProcessingStage.CONVERT
        assert sample_file_index.overall_status == OverallStatus.PROCESSING
        assert sample_file_index.last_updated >= original_updated

    def test_mark_completed(self, sample_file_index: FileIndex) -> None:
        """Test marking file as completed."""
        sample_file_index.mark_completed()

        assert sample_file_index.current_stage == ProcessingStage.COMPLETED
        assert sample_file_index.overall_status == OverallStatus.COMPLETED

    def test_mark_failed(self, sample_file_index: FileIndex) -> None:
        """Test marking file as failed."""
        error_msg = "Processing failed: timeout"
        sample_file_index.mark_failed(error_msg)

        assert sample_file_index.overall_status == OverallStatus.FAILED
        assert sample_file_index.error_message == error_msg
        assert sample_file_index.retry_count == 1

    def test_mark_failed_increments_retry(self, sample_file_index: FileIndex) -> None:
        """Test that mark_failed increments retry count."""
        sample_file_index.mark_failed("Error 1")
        sample_file_index.mark_failed("Error 2")
        sample_file_index.mark_failed("Error 3")

        assert sample_file_index.retry_count == 3
        assert sample_file_index.error_message == "Error 3"

    def test_create_file_index_with_collection_name(self) -> None:
        """Test creating FileIndex with required collection_name field."""
        file_index = FileIndex(
            tenant_id="tenant-001",
            file_id="file-001",
            blob_name="document.pdf",
            collection_name="test-collection",
        )

        assert file_index.collection_name == "test-collection"

    def test_create_file_index_with_promoted_fields(self) -> None:
        """Test creating FileIndex with all promoted metadata fields."""
        publish_date = datetime(2024, 1, 15, 10, 30, 0)
        approval_date = datetime(2024, 1, 10, 14, 0, 0)
        created_date = datetime(2023, 12, 1, 9, 0, 0)

        file_index = FileIndex(
            tenant_id="tenant-001",
            file_id="file-001",
            blob_name="document.pdf",
            collection_name="operations",
            ezshare_id="EZSHARE-510177122-450",
            document_type="operational",
            language="en",
            operation_number="UR-P1180",
            document_name="Urban Development Project Report",
            document_author="Smith, John",
            document_url="https://example.com/docs/UR-P1180",
            disclosed=True,
            country="Uruguay",
            operation_type="Investment",
            dept_id="EXR/CMG",
            sector="TRANSPORT",
            year=2024,
            file_extension=".pdf",
            access_to_information_policy="public",
            document_publish_date=publish_date,
            document_approval_date=approval_date,
            document_created_date=created_date,
        )

        assert file_index.collection_name == "operations"
        assert file_index.ezshare_id == "EZSHARE-510177122-450"
        assert file_index.document_type == "operational"
        assert file_index.language == "en"
        assert file_index.operation_number == "UR-P1180"
        assert file_index.document_name == "Urban Development Project Report"
        assert file_index.document_author == "Smith, John"
        assert file_index.document_url == "https://example.com/docs/UR-P1180"
        assert file_index.disclosed is True
        assert file_index.country == "Uruguay"
        assert file_index.operation_type == "Investment"
        assert file_index.dept_id == "EXR/CMG"
        assert file_index.sector == "TRANSPORT"
        assert file_index.year == 2024
        assert file_index.file_extension == ".pdf"
        assert file_index.access_to_information_policy == "public"
        assert file_index.document_publish_date == publish_date
        assert file_index.document_approval_date == approval_date
        assert file_index.document_created_date == created_date

    def test_document_type_defaults_none(self) -> None:
        """Test document_type defaults to None."""
        file_index = FileIndex(
            tenant_id="tenant-001",
            file_id="file-001",
            blob_name="document.pdf",
        )
        assert file_index.document_type is None

    def test_language_defaults_en(self) -> None:
        """Test language defaults to 'en'."""
        file_index = FileIndex(
            tenant_id="tenant-001",
            file_id="file-001",
            blob_name="document.pdf",
        )
        assert file_index.language == "en"

    def test_validate_operation_number_valid(self) -> None:
        """Test valid operation numbers are accepted."""
        valid_numbers = ["UR-P1180", "BR-P9999", "AR-P0001"]

        for op_num in valid_numbers:
            file_index = FileIndex(
                tenant_id="tenant-001",
                file_id="file-001",
                blob_name="document.pdf",
                collection_name="test",
                operation_number=op_num,
            )
            assert file_index.operation_number == op_num

    def test_validate_operation_number_invalid(self) -> None:
        """Test invalid operation numbers raise validation error."""
        invalid_numbers = ["P1180", "UR-1180", "UR-X1180", "URXP1180"]

        for op_num in invalid_numbers:
            with pytest.raises(ValidationError):
                FileIndex(
                    tenant_id="tenant-001",
                    file_id="file-001",
                    blob_name="document.pdf",
                    collection_name="test",
                    operation_number=op_num,
                )

    def test_validate_file_extension_auto_prefix(self) -> None:
        """Test file extension automatically gets dot prefix."""
        file_index = FileIndex(
            tenant_id="tenant-001",
            file_id="file-001",
            blob_name="document.pdf",
            collection_name="test",
            file_extension="pdf",
        )

        assert file_index.file_extension == ".pdf"

    def test_validate_file_extension_keeps_existing_dot(self) -> None:
        """Test file extension with existing dot is unchanged."""
        file_index = FileIndex(
            tenant_id="tenant-001",
            file_id="file-001",
            blob_name="document.pdf",
            collection_name="test",
            file_extension=".pdf",
        )

        assert file_index.file_extension == ".pdf"


@pytest.mark.unit
class TestProcessingStage:
    """Tests for ProcessingStage enum."""

    def test_all_stages_defined(self) -> None:
        """Test all expected stages are defined."""
        expected_stages = ["dispatcher", "convert", "chunk", "vectorize", "ingest", "completed"]
        actual_stages = [s.value for s in ProcessingStage]

        for stage in expected_stages:
            assert stage in actual_stages

    def test_stage_string_values(self) -> None:
        """Test stage string values match expected format."""
        assert ProcessingStage.DISPATCHER.value == "dispatcher"
        assert ProcessingStage.COMPLETED.value == "completed"


@pytest.mark.unit
class TestOverallStatus:
    """Tests for OverallStatus enum."""

    def test_all_statuses_defined(self) -> None:
        """Test all expected statuses are defined."""
        expected_statuses = ["queued", "processing", "completed", "failed"]
        actual_statuses = [s.value for s in OverallStatus]

        for status in expected_statuses:
            assert status in actual_statuses
