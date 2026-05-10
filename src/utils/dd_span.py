"""Datadog APM span helper for Azure Storage Queue triggers.

Azure Storage Queues do not propagate distributed tracing headers across the
message bus, so there is no automatic trace stitching between the HTTP request
that enqueues a job and the queue consumer that processes it.

This module provides a single async context manager (`queue_span`) that:
  1. Opens a root span for each queue trigger invocation.
  2. Attaches standard tags so every trigger is searchable in APM.
  3. Records exceptions on the span before re-raising.
  4. Degrades gracefully when ddtrace is absent (local dev without agent).

The domain `correlation_id` from `QueueMessageEnvelope` is attached as a span
tag — it is the cross-hop business identifier that lets you correlate a queue
span with the upstream HTTP request and the pipeline state store without
relying on HTTP tracing headers (which Azure Storage Queues don't carry).
"""

import os
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from src.application.dto.queue_message import QueueMessageEnvelope


@asynccontextmanager
async def queue_span(
    queue_name: str,
    envelope: QueueMessageEnvelope,
) -> AsyncGenerator[Any, None]:
    """Open a root Datadog APM span for a queue trigger invocation.

    Args:
        queue_name: The Azure Storage Queue name (e.g. "text-to-chunks").
        envelope: Parsed message envelope carrying file_id, tenant_id, correlation_id.

    Yields:
        The active ddtrace Span, or None when ddtrace is unavailable.
    """
    try:
        from ddtrace import tracer
    except ImportError:
        yield None
        return

    service = os.getenv("DD_SERVICE", "api-ea-nonstructured")
    operation = f"queue.{queue_name.replace('-', '_')}_trigger"

    with tracer.trace(operation, service=service, resource=queue_name) as span:
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
