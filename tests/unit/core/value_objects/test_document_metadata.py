"""Unit tests for DocumentMetadata model hierarchy."""

from datetime import datetime

import pytest

from src.core.value_objects.document_metadata import (
    DocumentMetadata,
    METADATA_MODELS,
    OperationalDocumentMetadata,
    PublicationDocumentMetadata,
    get_metadata_model,
    list_metadata_types,
)


@pytest.mark.unit
class TestDocumentMetadata:
    """Tests for DocumentMetadata base class."""

    def test_create_with_defaults(self) -> None:
        """Test creating DocumentMetadata with default values."""
        meta = DocumentMetadata(file_id="f1")

        assert meta.document_type is None
        assert meta.language == "en"
        assert meta.country is None
        assert meta.year is None
        assert meta.document_author is None
        assert meta.disclosed is None
        assert meta.file_extension is None

    def test_create_with_all_fields(self) -> None:
        """Test creating DocumentMetadata with all fields."""
        publish_date = datetime(2024, 1, 15)
        meta = DocumentMetadata(
            file_id="f1",
            document_type="report",
            language="es",
            country="Uruguay",
            year=2024,
            document_author="Smith, John",
            document_name="Annual Report",
            document_url="https://example.com/report",
            disclosed=True,
            file_extension=".pdf",
            access_to_information_policy="public",
            document_publish_date=publish_date,
        )

        assert meta.document_type == "report"
        assert meta.language == "es"
        assert meta.country == "Uruguay"
        assert meta.year == 2024
        assert meta.document_author == "Smith, John"
        assert meta.document_publish_date == publish_date

    def test_promoted_field_names_base(self) -> None:
        """Test promoted_field_names returns base fields."""
        names = DocumentMetadata.promoted_field_names()

        assert "document_type" in names
        assert "language" in names
        assert "country" in names
        assert "year" in names
        assert "document_author" in names
        assert "disclosed" in names
        assert "file_extension" in names
        assert "access_to_information_policy" in names
        assert "document_publish_date" in names
        assert "document_approval_date" in names
        assert "document_created_date" in names
        assert "document_name" in names
        assert "document_url" in names

        # Should NOT include operational-specific fields
        assert "operation_number" not in names
        assert "sector" not in names
        assert "operation_type" not in names
        assert "dept_id" not in names

    def test_to_dict_exclude_none(self) -> None:
        """Test to_dict excludes None by default."""
        meta = DocumentMetadata(
            file_id="f1",
            document_type="report",
            country="Brazil",
        )

        d = meta.to_dict()
        assert d["document_type"] == "report"
        assert d["country"] == "Brazil"
        assert "year" not in d
        assert "disclosed" not in d

    def test_to_dict_include_none(self) -> None:
        """Test to_dict includes None when requested."""
        meta = DocumentMetadata(file_id="f1", document_type="report")

        d = meta.to_dict(exclude_none=False)
        assert d["document_type"] == "report"
        assert "year" in d
        assert d["year"] is None

    def test_from_source_extracts_promoted_fields(self) -> None:
        """Test from_source extracts promoted fields from a source dict."""
        source = {
            "document_type": "report",
            "country": "Uruguay",
            "year": 2024,
            "disclosed": True,
        }

        meta = DocumentMetadata.from_source("f1", source)

        assert meta.file_id == "f1"
        assert meta.document_type == "report"
        assert meta.country == "Uruguay"
        assert meta.year == 2024
        assert meta.disclosed is True

    def test_year_validation(self) -> None:
        """Test year range validation."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DocumentMetadata(file_id="f1", year=1800)

        with pytest.raises(ValidationError):
            DocumentMetadata(file_id="f1", year=2200)

        # Valid years
        meta = DocumentMetadata(file_id="f1", year=2024)
        assert meta.year == 2024


@pytest.mark.unit
class TestOperationalDocumentMetadata:
    """Tests for OperationalDocumentMetadata subclass."""

    def test_includes_base_and_operational_fields(self) -> None:
        """Test that operational metadata includes both base and subclass fields."""
        meta = OperationalDocumentMetadata(
            file_id="f1",
            document_type="operational",
            country="Brazil",
            operation_number="BR-P1234",
            sector="TRANSPORT",
            operation_type="Investment",
            dept_id="INE/TSP",
        )

        assert meta.document_type == "operational"
        assert meta.country == "Brazil"
        assert meta.operation_number == "BR-P1234"
        assert meta.sector == "TRANSPORT"
        assert meta.operation_type == "Investment"
        assert meta.dept_id == "INE/TSP"

    def test_promoted_field_names_includes_operational(self) -> None:
        """Test promoted_field_names includes operational-specific fields."""
        names = OperationalDocumentMetadata.promoted_field_names()

        # Base fields
        assert "document_type" in names
        assert "country" in names
        assert "year" in names

        # Operational-specific fields
        assert "operation_number" in names
        assert "sector" in names
        assert "operation_type" in names
        assert "dept_id" in names

    def test_promoted_field_names_is_superset_of_base(self) -> None:
        """Test operational fields are a superset of base fields."""
        base_names = DocumentMetadata.promoted_field_names()
        op_names = OperationalDocumentMetadata.promoted_field_names()

        assert base_names.issubset(op_names)
        assert len(op_names) > len(base_names)

    def test_from_source_operational(self) -> None:
        """Test from_source extracts operational fields."""
        source = {
            "operation_number": "UR-P1180",
            "sector": "TRANSPORT",
            "dept_id": "INE/TSP",
        }

        meta = OperationalDocumentMetadata.from_source("f1", source)

        assert meta.file_id == "f1"
        assert meta.operation_number == "UR-P1180"
        assert meta.sector == "TRANSPORT"
        assert meta.dept_id == "INE/TSP"


@pytest.mark.unit
class TestPublicationDocumentMetadata:
    """Tests for PublicationDocumentMetadata subclass."""

    def test_includes_base_and_publication_fields(self) -> None:
        """Test that publication metadata includes both base and subclass fields."""
        pub_date = datetime(2024, 3, 15)
        meta = PublicationDocumentMetadata(
            file_id="f1",
            document_type="publication",
            country="Global",
            year=2024,
            journal="Journal of Development Economics",
            doi="10.1234/jde.2024.001",
            issn="0304-3878",
            peer_reviewed=True,
            publication_type="journal_article",
            publication_date=pub_date,
        )

        # Base fields
        assert meta.document_type == "publication"
        assert meta.country == "Global"
        assert meta.year == 2024

        # Publication-specific fields
        assert meta.journal == "Journal of Development Economics"
        assert meta.doi == "10.1234/jde.2024.001"
        assert meta.issn == "0304-3878"
        assert meta.peer_reviewed is True
        assert meta.publication_type == "journal_article"
        assert meta.publication_date == pub_date

    def test_promoted_field_names_includes_publication(self) -> None:
        """Test promoted_field_names includes publication-specific fields."""
        names = PublicationDocumentMetadata.promoted_field_names()

        # Base fields
        assert "document_type" in names
        assert "country" in names
        assert "year" in names
        assert "language" in names

        # Publication-specific fields
        assert "journal" in names
        assert "doi" in names
        assert "issn" in names
        assert "peer_reviewed" in names
        assert "publication_type" in names
        assert "publication_date" in names

    def test_promoted_field_names_is_superset_of_base(self) -> None:
        """Test publication fields are a superset of base fields."""
        base_names = DocumentMetadata.promoted_field_names()
        pub_names = PublicationDocumentMetadata.promoted_field_names()

        assert base_names.issubset(pub_names)
        assert len(pub_names) > len(base_names)

    def test_publication_excludes_operational_fields(self) -> None:
        """Test publication fields do NOT include operational-specific fields."""
        names = PublicationDocumentMetadata.promoted_field_names()

        assert "operation_number" not in names
        assert "sector" not in names
        assert "operation_type" not in names
        assert "dept_id" not in names

    def test_from_source_publication(self) -> None:
        """Test from_source extracts publication fields."""
        source = {
            "journal": "Latin American Economic Review",
            "doi": "10.1007/s40503-024-00123-4",
            "peer_reviewed": True,
            "publication_type": "working_paper",
        }

        meta = PublicationDocumentMetadata.from_source("f1", source)

        assert meta.file_id == "f1"
        assert meta.journal == "Latin American Economic Review"
        assert meta.doi == "10.1007/s40503-024-00123-4"
        assert meta.peer_reviewed is True
        assert meta.publication_type == "working_paper"


@pytest.mark.unit
class TestGetMetadataModel:
    """Tests for get_metadata_model registry function."""

    def test_none_returns_operational(self) -> None:
        """Test None document_type returns OperationalDocumentMetadata."""
        model = get_metadata_model(None)
        assert model is OperationalDocumentMetadata

    def test_operational_returns_operational(self) -> None:
        """Test 'operational' returns OperationalDocumentMetadata."""
        model = get_metadata_model("operational")
        assert model is OperationalDocumentMetadata

    def test_publication_returns_publication(self) -> None:
        """Test 'publication' returns PublicationDocumentMetadata."""
        model = get_metadata_model("publication")
        assert model is PublicationDocumentMetadata

    def test_unknown_type_returns_base(self) -> None:
        """Test unknown document_type returns base DocumentMetadata."""
        model = get_metadata_model("some_unknown_type")
        assert model is DocumentMetadata

    def test_registry_contains_operational(self) -> None:
        """Test the METADATA_MODELS registry has 'operational'."""
        assert "operational" in METADATA_MODELS
        assert METADATA_MODELS["operational"] is OperationalDocumentMetadata

    def test_registry_contains_publication(self) -> None:
        """Test the METADATA_MODELS registry has 'publication'."""
        assert "publication" in METADATA_MODELS
        assert METADATA_MODELS["publication"] is PublicationDocumentMetadata

    def test_list_metadata_types(self) -> None:
        """Test list_metadata_types returns all registered types."""
        types = list_metadata_types()

        assert "operational" in types
        assert "publication" in types
        assert types == sorted(types)  # Should be sorted
