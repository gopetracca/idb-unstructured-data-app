"""Unit tests for typed document upload form schemas."""

import pytest
from pydantic import ValidationError

from src.presentation.http.schemas.document_upload_schemas import (
    OperationalDocumentUploadForm,
    PublicationDocumentUploadForm,
)


class TestOperationalDocumentUploadForm:
    """Tests for OperationalDocumentUploadForm."""

    def test_minimal_required_fields(self) -> None:
        """Only required fields should be accepted."""
        form = OperationalDocumentUploadForm(
            collection_name="ops-docs",
            ezshare_id="EZSHARE-123-456",
        )
        assert form.collection_name == "ops-docs"
        assert form.ezshare_id == "EZSHARE-123-456"

    def test_all_operational_fields(self) -> None:
        """All operational-specific fields should be accepted."""
        form = OperationalDocumentUploadForm(
            collection_name="ops-docs",
            ezshare_id="EZSHARE-123-456",
            operation_number="UR-P1180",
            sector="TRANSPORT",
            operation_type="Loan",
            dept_id="INE/TSP",
            country="Peru",
            year=2024,
        )
        assert form.operation_number == "UR-P1180"
        assert form.sector == "TRANSPORT"
        assert form.operation_type == "Loan"
        assert form.dept_id == "INE/TSP"

    def test_to_metadata_dict_sets_document_type(self) -> None:
        """to_metadata_dict should inject document_type='operational'."""
        form = OperationalDocumentUploadForm(
            collection_name="ops-docs",
            ezshare_id="EZSHARE-123-456",
        )
        metadata = form.to_metadata_dict()
        assert metadata["document_type"] == "operational"

    def test_to_metadata_dict_excludes_routing_fields(self) -> None:
        """collection_name and ezshare_id should NOT appear in metadata dict."""
        form = OperationalDocumentUploadForm(
            collection_name="ops-docs",
            ezshare_id="EZSHARE-123-456",
            operation_number="UR-P1180",
        )
        metadata = form.to_metadata_dict()
        assert "collection_name" not in metadata
        assert "ezshare_id" not in metadata
        assert metadata["operation_number"] == "UR-P1180"

    def test_to_metadata_dict_excludes_none_values(self) -> None:
        """None fields should not be included in metadata dict."""
        form = OperationalDocumentUploadForm(
            collection_name="ops-docs",
            ezshare_id="EZSHARE-123-456",
        )
        metadata = form.to_metadata_dict()
        # None fields should be absent, not present as None
        assert "operation_number" not in metadata
        assert "sector" not in metadata

    def test_to_metadata_dict_parses_tags_from_string(self) -> None:
        """Comma-separated tags string should be parsed into a list."""
        form = OperationalDocumentUploadForm(
            collection_name="ops-docs",
            ezshare_id="EZSHARE-123-456",
            tags="transport, infrastructure, 2024",
        )
        metadata = form.to_metadata_dict()
        assert metadata["tags"] == ["transport", "infrastructure", "2024"]

    def test_rejects_extra_fields(self) -> None:
        """Extra unknown fields should raise ValidationError."""
        with pytest.raises(ValidationError):
            OperationalDocumentUploadForm(
                collection_name="ops-docs",
                ezshare_id="EZSHARE-123-456",
                unknown_field="value",
            )

    def test_rejects_invalid_year(self) -> None:
        """Years out of valid range should raise ValidationError."""
        with pytest.raises(ValidationError):
            OperationalDocumentUploadForm(
                collection_name="ops-docs",
                ezshare_id="EZSHARE-123-456",
                year=1800,
            )

    def test_publication_specific_fields_not_accepted(self) -> None:
        """Publication fields like journal/doi should be rejected."""
        with pytest.raises(ValidationError):
            OperationalDocumentUploadForm(
                collection_name="ops-docs",
                ezshare_id="EZSHARE-123-456",
                journal="Nature",  # publication field, not operational
            )


class TestPublicationDocumentUploadForm:
    """Tests for PublicationDocumentUploadForm."""

    def test_minimal_required_fields(self) -> None:
        """Only required fields should be accepted."""
        form = PublicationDocumentUploadForm(
            collection_name="publications",
            ezshare_id="EZSHARE-789-012",
        )
        assert form.collection_name == "publications"
        assert form.ezshare_id == "EZSHARE-789-012"

    def test_all_publication_fields(self) -> None:
        """All publication-specific fields should be accepted."""
        form = PublicationDocumentUploadForm(
            collection_name="publications",
            ezshare_id="EZSHARE-789-012",
            journal="Journal of Development Economics",
            doi="10.1234/jde.2024.001",
            issn="0304-3878",
            peer_reviewed=True,
            publication_type="journal_article",
        )
        assert form.journal == "Journal of Development Economics"
        assert form.doi == "10.1234/jde.2024.001"
        assert form.issn == "0304-3878"
        assert form.peer_reviewed is True
        assert form.publication_type == "journal_article"

    def test_to_metadata_dict_sets_document_type(self) -> None:
        """to_metadata_dict should inject document_type='publication'."""
        form = PublicationDocumentUploadForm(
            collection_name="publications",
            ezshare_id="EZSHARE-789-012",
        )
        metadata = form.to_metadata_dict()
        assert metadata["document_type"] == "publication"

    def test_to_metadata_dict_excludes_routing_fields(self) -> None:
        """collection_name and ezshare_id should NOT appear in metadata dict."""
        form = PublicationDocumentUploadForm(
            collection_name="publications",
            ezshare_id="EZSHARE-789-012",
            journal="Nature",
        )
        metadata = form.to_metadata_dict()
        assert "collection_name" not in metadata
        assert "ezshare_id" not in metadata
        assert metadata["journal"] == "Nature"

    def test_to_metadata_dict_excludes_none_values(self) -> None:
        """None fields should not be included in metadata dict."""
        form = PublicationDocumentUploadForm(
            collection_name="publications",
            ezshare_id="EZSHARE-789-012",
        )
        metadata = form.to_metadata_dict()
        assert "journal" not in metadata
        assert "doi" not in metadata

    def test_to_metadata_dict_parses_tags_from_string(self) -> None:
        """Comma-separated tags string should be parsed into a list."""
        form = PublicationDocumentUploadForm(
            collection_name="publications",
            ezshare_id="EZSHARE-789-012",
            tags="economics, working-paper",
        )
        metadata = form.to_metadata_dict()
        assert metadata["tags"] == ["economics", "working-paper"]

    def test_rejects_extra_fields(self) -> None:
        """Extra unknown fields should raise ValidationError."""
        with pytest.raises(ValidationError):
            PublicationDocumentUploadForm(
                collection_name="publications",
                ezshare_id="EZSHARE-789-012",
                unknown_field="value",
            )

    def test_operational_specific_fields_not_accepted(self) -> None:
        """Operational fields like operation_number should be rejected."""
        with pytest.raises(ValidationError):
            PublicationDocumentUploadForm(
                collection_name="publications",
                ezshare_id="EZSHARE-789-012",
                operation_number="UR-P1180",  # operational field, not publication
            )
