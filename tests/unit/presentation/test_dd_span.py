"""Unit tests for the Datadog queue span helper."""

import sys
from datetime import datetime, timezone
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from src.application.dto.queue_message import QueueMessageEnvelope


def _make_envelope(**overrides) -> QueueMessageEnvelope:
    defaults = dict(
        tenantId="tenant-1",
        fileId="file-abc",
        fileVersion=1,
        operationId="op-1",
        correlationId="corr-xyz",
        timestamp=datetime.now(timezone.utc).isoformat(),
        retryCount=0,
        payload={},
    )
    defaults.update(overrides)
    return QueueMessageEnvelope(**defaults)


class TestQueueSpanWithDdtrace:
    """dd_span behaves correctly when ddtrace is importable."""

    @pytest.mark.asyncio
    async def test_sets_all_required_tags(self) -> None:
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.trace.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.trace.return_value.__exit__ = MagicMock(return_value=False)

        mock_ddtrace = ModuleType("ddtrace")
        mock_ddtrace.tracer = mock_tracer  # type: ignore[attr-defined]

        envelope = _make_envelope()

        with patch.dict(sys.modules, {"ddtrace": mock_ddtrace}):
            # Re-import so the module picks up the patched ddtrace
            import importlib
            import src.utils.dd_span as dd_span_mod
            importlib.reload(dd_span_mod)

            async with dd_span_mod.queue_span("text-to-chunks", envelope) as span:
                assert span is mock_span

        mock_span.set_tag.assert_any_call("queue.name", "text-to-chunks")
        mock_span.set_tag.assert_any_call("messaging.system", "azure_storage_queues")
        mock_span.set_tag.assert_any_call("file_id", "file-abc")
        mock_span.set_tag.assert_any_call("tenant_id", "tenant-1")
        mock_span.set_tag.assert_any_call("correlation_id", "corr-xyz")

    @pytest.mark.asyncio
    async def test_operation_name_uses_underscores(self) -> None:
        mock_tracer = MagicMock()
        mock_tracer.trace.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_tracer.trace.return_value.__exit__ = MagicMock(return_value=False)

        mock_ddtrace = ModuleType("ddtrace")
        mock_ddtrace.tracer = mock_tracer  # type: ignore[attr-defined]

        envelope = _make_envelope()

        with patch.dict(sys.modules, {"ddtrace": mock_ddtrace}):
            import importlib
            import src.utils.dd_span as dd_span_mod
            importlib.reload(dd_span_mod)

            async with dd_span_mod.queue_span("chunk-to-vector", envelope):
                pass

        call_args = mock_tracer.trace.call_args
        assert call_args[0][0] == "queue.chunk_to_vector_trigger"

    @pytest.mark.asyncio
    async def test_records_exception_on_span_and_reraises(self) -> None:
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.trace.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.trace.return_value.__exit__ = MagicMock(return_value=False)

        mock_ddtrace = ModuleType("ddtrace")
        mock_ddtrace.tracer = mock_tracer  # type: ignore[attr-defined]

        envelope = _make_envelope()

        with patch.dict(sys.modules, {"ddtrace": mock_ddtrace}):
            import importlib
            import src.utils.dd_span as dd_span_mod
            importlib.reload(dd_span_mod)

            with pytest.raises(ValueError, match="boom"):
                async with dd_span_mod.queue_span("raw-to-text", envelope):
                    raise ValueError("boom")

        mock_span.set_exc_info.assert_called_once()
        exc_type, exc_val, _ = mock_span.set_exc_info.call_args[0]
        assert exc_type is ValueError
        assert str(exc_val) == "boom"


class TestQueueSpanWithoutDdtrace:
    """dd_span degrades gracefully when ddtrace is absent."""

    @pytest.mark.asyncio
    async def test_yields_none_when_ddtrace_missing(self) -> None:
        envelope = _make_envelope()

        # Remove ddtrace from sys.modules to simulate ImportError
        with patch.dict(sys.modules, {"ddtrace": None}):
            import importlib
            import src.utils.dd_span as dd_span_mod
            importlib.reload(dd_span_mod)

            async with dd_span_mod.queue_span("ingest-to-db", envelope) as span:
                assert span is None

    @pytest.mark.asyncio
    async def test_body_still_executes_when_ddtrace_missing(self) -> None:
        envelope = _make_envelope()
        executed = []

        with patch.dict(sys.modules, {"ddtrace": None}):
            import importlib
            import src.utils.dd_span as dd_span_mod
            importlib.reload(dd_span_mod)

            async with dd_span_mod.queue_span("ingest-to-db", envelope):
                executed.append(True)

        assert executed == [True]
