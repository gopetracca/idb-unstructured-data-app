"""Unit tests for domain error classes."""

import pytest

from src.core.errors import (
    DocumentNotFoundError,
    DomainError,
    FileSizeExceededError,
    InvalidFileTypeError,
    MetadataValidationError,
    StorageError,
)


class TestDomainError:
    """Tests for base DomainError class."""

    def test_create_domain_error(self) -> None:
        """Test creating a basic domain error."""
        error = DomainError("Test error message")

        assert error.message == "Test error message"
        assert str(error) == "Test error message"

    def test_domain_error_is_exception(self) -> None:
        """Test that DomainError is an Exception."""
        error = DomainError("Test")

        assert isinstance(error, Exception)


class TestDocumentNotFoundError:
    """Tests for DocumentNotFoundError."""

    def test_create_with_file_id_only(self) -> None:
        """Test creating error with file_id only."""
        error = DocumentNotFoundError(file_id="test-file-123")

        assert error.file_id == "test-file-123"
        assert error.tenant_id is None
        assert "test-file-123" in error.message
        assert "not found" in error.message

    def test_create_with_tenant_id(self) -> None:
        """Test creating error with both file_id and tenant_id."""
        error = DocumentNotFoundError(
            file_id="test-file-123",
            tenant_id="tenant-abc",
        )

        assert error.file_id == "test-file-123"
        assert error.tenant_id == "tenant-abc"
        assert "test-file-123" in error.message
        assert "tenant-abc" in error.message

    def test_is_domain_error(self) -> None:
        """Test that DocumentNotFoundError is a DomainError."""
        error = DocumentNotFoundError(file_id="test")

        assert isinstance(error, DomainError)


class TestInvalidFileTypeError:
    """Tests for InvalidFileTypeError."""

    def test_create_error(self) -> None:
        """Test creating InvalidFileTypeError."""
        error = InvalidFileTypeError(
            mime_type="text/plain",
            allowed_types=["application/pdf", "application/docx"],
        )

        assert error.mime_type == "text/plain"
        assert error.allowed_types == ["application/pdf", "application/docx"]
        assert "text/plain" in error.message
        assert "application/pdf" in error.message

    def test_message_format(self) -> None:
        """Test error message format."""
        error = InvalidFileTypeError(
            mime_type="image/png",
            allowed_types=["application/pdf"],
        )

        assert "Invalid file type" in error.message
        assert "Allowed types" in error.message


class TestFileSizeExceededError:
    """Tests for FileSizeExceededError."""

    def test_create_error(self) -> None:
        """Test creating FileSizeExceededError."""
        error = FileSizeExceededError(
            size_bytes=100 * 1024 * 1024,  # 100MB
            max_size_bytes=50 * 1024 * 1024,  # 50MB
        )

        assert error.size_bytes == 100 * 1024 * 1024
        assert error.max_size_bytes == 50 * 1024 * 1024

    def test_message_shows_mb(self) -> None:
        """Test that message shows sizes in MB."""
        error = FileSizeExceededError(
            size_bytes=52428800,  # 50MB
            max_size_bytes=26214400,  # 25MB
        )

        assert "50.00MB" in error.message
        assert "25.00MB" in error.message

    def test_message_format(self) -> None:
        """Test error message format."""
        error = FileSizeExceededError(
            size_bytes=1024 * 1024,
            max_size_bytes=512 * 1024,
        )

        assert "exceeds maximum" in error.message


class TestMetadataValidationError:
    """Tests for MetadataValidationError."""

    def test_create_error(self) -> None:
        """Test creating MetadataValidationError."""
        error = MetadataValidationError(
            field="document_type",
            reason="must be a string",
        )

        assert error.field == "document_type"
        assert error.reason == "must be a string"

    def test_message_format(self) -> None:
        """Test error message format."""
        error = MetadataValidationError(
            field="tags",
            reason="must be a list",
        )

        assert "tags" in error.message
        assert "must be a list" in error.message
        assert "validation failed" in error.message.lower()


class TestStorageError:
    """Tests for StorageError."""

    def test_create_error(self) -> None:
        """Test creating StorageError."""
        error = StorageError(
            operation="upload",
            reason="Connection timeout",
        )

        assert error.operation == "upload"
        assert error.reason == "Connection timeout"

    def test_message_format(self) -> None:
        """Test error message format."""
        error = StorageError(
            operation="delete",
            reason="Blob not found",
        )

        assert "delete" in error.message
        assert "Blob not found" in error.message
        assert "failed" in error.message
