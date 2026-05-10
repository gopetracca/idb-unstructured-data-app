"""Unit tests for ProcessingEvent and StageDurationStats entities."""

from datetime import datetime

import pytest

from src.core.entities.processing_event import ProcessingEvent, StageDurationStats


@pytest.mark.unit
class TestProcessingEvent:
    """Tests for ProcessingEvent entity."""

    def test_create_with_all_fields(self):
        now = datetime.utcnow()
        event = ProcessingEvent(
            event_id=1,
            file_id="file-001",
            tenant_id="test-tenant",
            stage="convert",
            status="success",
            event_timestamp=now,
            duration_ms=1500,
            error_message=None,
            metadata_json='{"key": "value"}',
        )

        assert event.event_id == 1
        assert event.file_id == "file-001"
        assert event.tenant_id == "test-tenant"
        assert event.stage == "convert"
        assert event.status == "success"
        assert event.event_timestamp == now
        assert event.duration_ms == 1500
        assert event.error_message is None
        assert event.metadata_json == '{"key": "value"}'

    def test_create_with_defaults(self):
        event = ProcessingEvent(
            file_id="file-001",
            tenant_id="test-tenant",
            stage="dispatcher",
            status="success",
        )

        assert event.event_id is None
        assert event.duration_ms is None
        assert event.error_message is None
        assert event.metadata_json is None
        assert isinstance(event.event_timestamp, datetime)

    def test_failed_event_with_error(self):
        event = ProcessingEvent(
            file_id="file-001",
            tenant_id="test-tenant",
            stage="chunk",
            status="failed",
            error_message="Chunking failed: invalid format",
        )

        assert event.status == "failed"
        assert event.error_message == "Chunking failed: invalid format"

    def test_stage_field_identifies_executed_stage(self):
        event = ProcessingEvent(
            file_id="file-001",
            tenant_id="test-tenant",
            stage="vectorize",
            status="success",
        )

        assert event.stage == "vectorize"


@pytest.mark.unit
class TestStageDurationStats:
    """Tests for StageDurationStats entity."""

    def test_create(self):
        stats = StageDurationStats(
            stage="convert",
            avg_duration_ms=2500.5,
            min_duration_ms=1000,
            max_duration_ms=5000,
            sample_count=10,
        )

        assert stats.stage == "convert"
        assert stats.avg_duration_ms == 2500.5
        assert stats.min_duration_ms == 1000
        assert stats.max_duration_ms == 5000
        assert stats.sample_count == 10

    def test_avg_is_float(self):
        stats = StageDurationStats(
            stage="chunk",
            avg_duration_ms=1200,
            min_duration_ms=500,
            max_duration_ms=3000,
            sample_count=5,
        )

        assert isinstance(stats.avg_duration_ms, float)
