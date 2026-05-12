"""Datadog APM span helper for Azure Storage Queue triggers.

Azure Storage Queues do not propagate distributed tracing headers across the
message bus, so there is no automatic trace stitching between the HTTP request
that enqueues a job and the queue consumer that processes it.

This module provides a single async context manager (`queue_span`) that:
  1. Extracts parent trace context from the message envelope's ``_datadog``
     field (injected by the producer via ``HTTPPropagator.inject``).
  2. Opens a child span linked to the parent trace, or a root span when no
     context is available (backward compatibility).
  3. Attaches standard tags so every trigger is searchable in APM.
  4. Records exceptions on the span before re-raising.
  5. Degrades gracefully when ddtrace is absent (local dev without agent).

The domain `correlation_id` from `QueueMessageEnvelope` is attached as a span
tag — it is the cross-hop business identifier that lets you correlate a queue
span with the upstream HTTP request and the pipeline state store.
"""

import os
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from src.application.dto.queue_message import QueueMessageEnvelope
from src.utils.trace_context import correlation_id_var


@asynccontextmanager
async def queue_span(
    queue_name: str,
    envelope: QueueMessageEnvelope,
) -> AsyncGenerator[Any, None]:
    """Open a Datadog APM span for a queue trigger invocation.

    When the message envelope carries a ``_datadog`` trace-context dict
    (injected by the producer), the span is created as a **child** of the
    original trace.  Otherwise a new root span is created (backward
    compatible with messages already in the queue before this change).

    Args:
        queue_name: The Azure Storage Queue name (e.g. "text-to-chunks").
        envelope: Parsed message envelope carrying file_id, tenant_id, correlation_id.

    Yields:
        The active ddtrace Span, or None when ddtrace is unavailable.
    """
    try:
        from ddtrace import tracer
        from ddtrace.propagation.http import HTTPPropagator
    except ImportError:
        yield None
        return

    service = os.getenv("DD_SERVICE", "api-ea-nonstructured")
    operation = f"queue.{queue_name.replace('-', '_')}_trigger"

    # Extract parent context from the message envelope (if present)
    parent_context = None
    if envelope.datadog_context:
        extracted = HTTPPropagator.extract(envelope.datadog_context)
        if extracted and extracted.trace_id:
            parent_context = extracted

    # Activate parent context so tracer.trace() creates a child span
    if parent_context:
        tracer.context_provider.activate(parent_context)

    with tracer.trace(
        operation,
        service=service,
        resource=queue_name,
    ) as span:
        token = correlation_id_var.set(envelope.correlation_id)
        span.set_tag("queue.name", queue_name)
        span.set_tag("messaging.system", "azure_storage_queues")
        span.set_tag("file_id", envelope.file_id)
        span.set_tag("tenant_id", envelope.tenant_id)
        span.set_tag("correlation_id", envelope.correlation_id)
        try:
            yield span
        except Exception:
            span.set_exc_info(*sys.exc_info())
            raise
        finally:
            correlation_id_var.reset(token)
