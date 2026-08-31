"""How the extraction engine and raw-analysis persistence are configured.

Two settings, both of which change what is stored rather than how fast it is stored, which
is why both are tested for what happens when they are *wrong* rather than only when right.
"""

import pytest

from src.config.settings import EXTRACTION_ADAPTERS, Settings

pytestmark = pytest.mark.unit


class TestExtractionAdapterSetting:
    def test_it_defaults_to_document_intelligence(self):
        assert Settings().extraction_adapter == "document_intelligence"

    @pytest.mark.parametrize("engine", sorted(EXTRACTION_ADAPTERS))
    def test_every_named_engine_is_accepted(self, engine):
        assert Settings(extraction_adapter=engine).extraction_adapter == engine

    def test_case_and_surrounding_space_do_not_change_the_engine(self):
        assert Settings(extraction_adapter="  Docling ").extraction_adapter == "docling"

    @pytest.mark.parametrize("value", ["doclng", "azure", "", "true"])
    def test_anything_else_fails_at_startup_naming_what_it_accepts(self, value):
        """Louder than `CHUNKING_ADAPTER`, deliberately: a typo here would silently change
        what every document's stored text *is*, and nothing downstream could tell."""
        with pytest.raises(ValueError) as failure:
            Settings(extraction_adapter=value)

        message = str(failure.value)
        assert "EXTRACTION_ADAPTER" in message
        assert "docling" in message and "document_intelligence" in message


class TestRawExtractionPersistence:
    """Whether the verbatim engine response is stored is a property of the stage, not of
    the engine — but the name deployed configuration already uses says otherwise, so both
    names have to work."""

    def test_it_is_on_by_default(self):
        assert Settings().raw_extraction_persisted is True

    def test_the_legacy_document_intelligence_name_still_governs(self):
        settings = Settings(document_intelligence={"persist_raw_result": False})

        assert settings.raw_extraction_persisted is False

    def test_the_engine_neutral_name_wins_when_both_are_set(self):
        settings = Settings(
            persist_raw_extraction=True,
            document_intelligence={"persist_raw_result": False},
        )

        assert settings.raw_extraction_persisted is True

    def test_the_engine_neutral_name_governs_on_its_own(self):
        assert Settings(persist_raw_extraction=False).raw_extraction_persisted is False
