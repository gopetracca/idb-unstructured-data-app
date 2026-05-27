"""Unit tests for SearchableMetadata hierarchy and SearchResultMetadata value objects."""

import pytest

from src.core.value_objects.document_metadata import (
    DocumentMetadata,
    OperationalDocumentMetadata,
    PublicationDocumentMetadata,
)
from src.core.value_objects.searchable_metadata import (
    BaseSearchableMetadata,
    OperationalSearchableMetadata,
    PublicationSearchableMetadata,
    SearchableMetadata,
    create_searchable_metadata,
    get_searchable_metadata_model,
)
from src.core.value_objects.search_result_metadata import SearchResultMetadata


class TestBaseSearchableMetadata:
    """Tests for BaseSearchableMetadata base class."""

    def test_create_with_defaults(self) -> None:
        """Test base class with default values."""
        metadata = BaseSearchableMetadata()

        assert metadata.document_type is None
        assert metadata.country is None
        assert metadata.year is None
        assert metadata.tags == []
        assert metadata.page_number is None
        assert metadata.blob_name is None

    def test_section_path_coerces_list_to_string(self) -> None:
        """section_path list[str] from ChunkMetadata must be joined into a string."""
        metadata = BaseSearchableMetadata(
            section_path=["Búsqueda Exhaustiva Diagnóstico"]
        )
        assert metadata.section_path == "Búsqueda Exhaustiva Diagnóstico"

    def test_section_path_multi_element_list_joined(self) -> None:
        """Multi-element list is joined with ' > ' separator."""
        metadata = BaseSearchableMetadata(
            section_path=["Introduction", "Background", "Related Work"]
        )
        assert metadata.section_path == "Introduction > Background > Related Work"

    def test_section_path_empty_list_becomes_none(self) -> None:
        """Empty list is normalised to None."""
        metadata = BaseSearchableMetadata(section_path=[])
        assert metadata.section_path is None

    def test_section_path_string_passthrough(self) -> None:
        """Plain string values are kept as-is."""
        metadata = BaseSearchableMetadata(section_path="Chapter 1 > Section 1.2")
        assert metadata.section_path == "Chapter 1 > Section 1.2"

    def test_section_path_none_stays_none(self) -> None:
        """None stays None."""
        metadata = BaseSearchableMetadata(section_path=None)
        assert metadata.section_path is None


class TestOperationalSearchableMetadata:
    """Tests for OperationalSearchableMetadata subclass."""

    def test_create_with_defaults(self) -> None:
        """Test operational metadata default document_type is None (user-provided now)."""
        metadata = OperationalSearchableMetadata()

        assert metadata.document_type is None  # No longer hardcoded; user-provided
        assert metadata.country is None
        assert metadata.year is None
        assert metadata.operation_number is None
        assert metadata.sector is None

    def test_includes_operational_fields(self) -> None:
        """Test that operational fields are present."""
        metadata = OperationalSearchableMetadata(
            operation_number="UR-P1180",
            sector="TRANSPORT",
            operation_type="Loan",
            dept_id="INE/TSP",
            document_publish_date="2024-06-15T12:00:00",
        )

        assert metadata.operation_number == "UR-P1180"
        assert metadata.sector == "TRANSPORT"
        assert metadata.operation_type == "Loan"
        assert metadata.dept_id == "INE/TSP"
        assert metadata.document_publish_date == "2024-06-15T12:00:00"


class TestPublicationSearchableMetadata:
    """Tests for PublicationSearchableMetadata subclass."""

    def test_create_with_defaults(self) -> None:
        """Test publication metadata default document_type is None (user-provided now)."""
        metadata = PublicationSearchableMetadata()

        assert metadata.document_type is None  # No longer hardcoded; user-provided
        assert metadata.journal is None
        assert metadata.doi is None

    def test_includes_publication_fields(self) -> None:
        """Test that publication fields are present."""
        metadata = PublicationSearchableMetadata(
            journal="Development Economics Review",
            doi="10.1234/der.2024.001",
            issn="0304-3878",
            peer_reviewed=True,
            publication_type="journal_article",
            publication_date="2024-03-15",
        )

        assert metadata.journal == "Development Economics Review"
        assert metadata.doi == "10.1234/der.2024.001"
        assert metadata.issn == "0304-3878"
        assert metadata.peer_reviewed is True
        assert metadata.publication_type == "journal_article"
        assert metadata.publication_date == "2024-03-15"

    def test_excludes_operational_fields(self) -> None:
        """Test that publication metadata doesn't have operational fields."""
        metadata = PublicationSearchableMetadata()

        assert not hasattr(metadata, "operation_number") or metadata.model_fields.get("operation_number") is None
        assert not hasattr(metadata, "sector") or "sector" not in metadata.model_fields


class TestSearchableMetadata:
    """Tests for SearchableMetadata (alias for backward compatibility)."""

    def test_alias_is_operational(self) -> None:
        """Test SearchableMetadata is alias for OperationalSearchableMetadata."""
        assert SearchableMetadata is OperationalSearchableMetadata

class TestCreateSearchableMetadata:
    """Tests for create_searchable_metadata factory function."""

    def test_from_document_and_chunk_with_operational_metadata(self) -> None:
        doc_meta = OperationalDocumentMetadata(
            file_id="file-1",
            document_category="operational",  # Schema discriminator
            document_type="PCR",              # User-facing type
            country="Uruguay",
            year=2024,
            sector="TRANSPORT",
            operation_number="UR-P1180",
            operation_type="Loan",
            dept_id="INE/TSP",
            language="en",
            disclosed=True,
            tags=["infrastructure", "transport"],
            source="ezshare",
            department="Operations",
            document_name="Project Appraisal",
            document_author="John Doe",
            file_extension=".pdf",
        )
        chunk = {
            "page_number": 3,
            "section_path": "Introduction",
            "has_table": False,
            "token_count": 512,
            "chunking_strategy": "fixed",
        }

        sm = create_searchable_metadata(
            doc_metadata=doc_meta,
            chunk_metadata=chunk,
            ezshare_id="EZSHARE-123",
            collection_name="embeddings",
            blob_name="appraisal.pdf",
        )

        assert isinstance(sm, OperationalSearchableMetadata)
        assert sm.document_type == "PCR"  # User-facing type flows through
        assert sm.country == "Uruguay"
        assert sm.year == 2024
        assert sm.sector == "TRANSPORT"
        assert sm.operation_number == "UR-P1180"
        assert sm.operation_type == "Loan"
        assert sm.dept_id == "INE/TSP"
        assert sm.language == "en"
        assert sm.disclosed is True
        assert sm.tags == ["infrastructure", "transport"]
        assert sm.source == "ezshare"
        assert sm.department == "Operations"
        assert sm.document_name == "Project Appraisal"
        assert sm.document_author == "John Doe"
        assert sm.file_extension == ".pdf"
        assert sm.ezshare_id == "EZSHARE-123"
        assert sm.collection_name == "embeddings"
        assert sm.blob_name == "appraisal.pdf"
        assert sm.page_number == 3
        assert sm.section_path == "Introduction"
        assert sm.has_table is False
        assert sm.token_count == 512
        assert sm.chunking_strategy == "fixed"

    def test_from_document_and_chunk_with_publication_metadata(self) -> None:
        """Test factory creates PublicationSearchableMetadata for publications."""
        from datetime import datetime

        doc_meta = PublicationDocumentMetadata(
            file_id="file-2",
            document_category="publication",     # Schema discriminator
            document_type="journal_article",     # User-facing type
            country="Global",
            year=2024,
            journal="Journal of Development",
            doi="10.1234/jod.2024.001",
            peer_reviewed=True,
            publication_type="journal_article",
            publication_date=datetime(2024, 3, 15),
        )
        chunk = {"page_number": 1, "section_path": "Abstract"}

        sm = create_searchable_metadata(
            doc_metadata=doc_meta,
            chunk_metadata=chunk,
            collection_name="publications",
        )

        assert isinstance(sm, PublicationSearchableMetadata)
        assert sm.document_type == "journal_article"  # User-facing type flows through
        assert sm.journal == "Journal of Development"
        assert sm.doi == "10.1234/jod.2024.001"
        assert sm.peer_reviewed is True
        assert sm.publication_type == "journal_article"
        assert sm.publication_date == "2024-03-15T00:00:00Z"
        assert sm.page_number == 1

    def test_from_document_and_chunk_with_none_doc_metadata(self) -> None:
        """Passing an object with no attributes defaults to operational."""
        sm = create_searchable_metadata(
            doc_metadata=object(),
            chunk_metadata={"page_number": 1},
            collection_name="embeddings",
        )

        # Defaults to operational when document_type is None
        assert isinstance(sm, OperationalSearchableMetadata)
        assert sm.document_type is None
        assert sm.country is None
        assert sm.tags == []
        assert sm.page_number == 1

    def test_from_document_and_chunk_with_empty_chunk(self) -> None:
        doc_meta = DocumentMetadata(file_id="f1", document_type="policy", country="Peru")
        sm = create_searchable_metadata(
            doc_metadata=doc_meta,
            chunk_metadata={},
        )

        # Unknown type defaults to operational
        assert sm.document_type == "policy"
        assert sm.country == "Peru"
        assert sm.page_number is None
        assert sm.has_table is None

    def test_tags_validator_handles_string_input(self) -> None:
        sm = BaseSearchableMetadata(tags="ai, ml, nlp")

        assert sm.tags == ["ai", "ml", "nlp"]

    def test_tags_validator_handles_none(self) -> None:
        sm = BaseSearchableMetadata(tags=None)

        assert sm.tags == []

    def test_document_publish_date_serialized_to_utc_datetime_offset(self) -> None:
        from datetime import datetime

        doc_meta = OperationalDocumentMetadata(
            file_id="f1",
            document_category="operational",  # Schema discriminator
            document_publish_date=datetime(2024, 6, 15, 12, 0, 0),
        )
        sm = create_searchable_metadata(
            doc_metadata=doc_meta,
            chunk_metadata={},
        )

        assert sm.document_publish_date == "2024-06-15T12:00:00Z"


class TestGetSearchableMetadataModel:
    """Tests for get_searchable_metadata_model function (now keyed by document_category)."""

    def test_none_returns_operational(self) -> None:
        model = get_searchable_metadata_model(None)
        assert model is OperationalSearchableMetadata

    def test_operational_category_returns_operational(self) -> None:
        model = get_searchable_metadata_model("operational")
        assert model is OperationalSearchableMetadata

    def test_publication_category_returns_publication(self) -> None:
        model = get_searchable_metadata_model("publication")
        assert model is PublicationSearchableMetadata

    def test_unknown_category_returns_operational(self) -> None:
        """Unknown categories default to operational."""
        model = get_searchable_metadata_model("unknown_category")
        assert model is OperationalSearchableMetadata


class TestSearchResultMetadata:
    """Tests for SearchResultMetadata derivation from SearchableMetadata."""

    def test_from_searchable_extracts_correct_fields(self) -> None:
        sm = SearchableMetadata(
            blob_name="report.pdf",
            page_number=5,
            ezshare_id="EZSHARE-999",
            section_path="Executive Summary",
            year=2023,
            document_type="report",
            country="Brazil",
        )

        result = SearchResultMetadata.from_searchable(sm)

        assert result.filename == "report.pdf"
        assert result.page_number == 5
        assert result.ezshare_id == "EZSHARE-999"
        assert result.section_path == "Executive Summary"
        assert result.year == 2023

    def test_from_searchable_all_none(self) -> None:
        sm = SearchableMetadata()

        result = SearchResultMetadata.from_searchable(sm)

        assert result.filename is None
        assert result.page_number is None
        assert result.ezshare_id is None
        assert result.section_path is None
        assert result.year is None

    def test_from_searchable_does_not_include_extra_fields(self) -> None:
        sm = SearchableMetadata(
            blob_name="doc.pdf",
            year=2020,
            department="Legal",  # not in SearchResultMetadata
            tags=["tag"],  # not in SearchResultMetadata
        )

        result = SearchResultMetadata.from_searchable(sm)

        assert not hasattr(result, "department")
        assert not hasattr(result, "tags")
        assert result.filename == "doc.pdf"
        assert result.year == 2020
