"""Request-scoped context variables for log correlation."""

from contextvars import ContextVar

# Set by queue_span() and HTTP middleware to propagate through async call chains.
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")
