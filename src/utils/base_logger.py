import json
import logging
import logging.config
import os
import warnings
from datetime import UTC, datetime
from typing import Any

from src.config.settings import get_settings
from src.utils.trace_context import correlation_id_var

try:
    from ddtrace import tracer
    from ddtrace._trace.processor import TraceProcessor as _TraceProcessor

    _DEFAULT_IGNORED = frozenset({"pyodbc.connection.commit", "pyodbc.connection.rollback"})

    def _build_ignored_spans() -> frozenset[str]:
        """Read DD_APM_IGNORE_RESOURCES via settings (comma-separated span names), falling back to defaults.

        Accepts both literal dots and regex-escaped dots (``\\.``) for compatibility with
        the official DD_APM_IGNORE_RESOURCES regex syntax.
        """
        raw = get_settings().dd_apm_ignore_resources
        # DD_APM_IGNORE_RESOURCES uses regex syntax; unescape \. -> . for literal comparison
        names = {name.strip().replace("\\.", ".") for name in raw.split(",") if name.strip()}
        return frozenset(names) if names else _DEFAULT_IGNORED

    class _DropConnectionOpsFilter(_TraceProcessor):
        """Drop spans listed in DD_APM_IGNORE_RESOURCES (defaults to pyodbc commit/rollback)."""

        _IGNORED: frozenset[str] = _build_ignored_spans()

        def process_trace(self, trace):
            filtered = [s for s in trace if s.resource not in self._IGNORED]
            return filtered if filtered else None

except ImportError:
    tracer = None
    _DropConnectionOpsFilter = None

settings = get_settings()
level = settings.logging_level.upper()
azure_sdk_level = settings.azure_sdk_log_level.upper()

NOISY_DEPENDENCY_LOGGERS = (
    "azure_functions_worker",
    "azure",
    "azure.core",
    "azure.core.pipeline.policies.http_logging_policy",
    "azure.identity",
    "azure.search",
    "azure.storage",
    "azure.storage.blob",
    "azure.storage.queue",
    "httpcore",
    "httpx",
    "urllib3",
)


def _single_line(value: str) -> str:
    return value.replace("\r", "\\r").replace("\n", "\\n")


class DatadogJsonFormatter(logging.Formatter):
    """Emit one-line JSON logs so Datadog pipelines can parse fields reliably."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": _single_line(record.getMessage()),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "service": os.getenv("DD_SERVICE", "api-ea-nonstructured"),
            "source": os.getenv("DD_SOURCE", "python"),
            "env": os.getenv("DD_ENV", settings.environment),
            "version": os.getenv("DD_VERSION", ""),
        }

        if record.exc_info:
            payload["exception"] = _single_line(self.formatException(record.exc_info))

        cid = correlation_id_var.get()
        if cid:
            payload["correlation_id"] = cid

        trace_id = getattr(record, "dd.trace_id", None)
        span_id = getattr(record, "dd.span_id", None)
        if trace_id and span_id:
            payload["dd.trace_id"] = str(trace_id)
            payload["dd.span_id"] = str(span_id)
            return json.dumps(payload, ensure_ascii=True)

        if tracer is None:
            return json.dumps(payload, ensure_ascii=True)

        correlation_context = tracer.get_log_correlation_context()
        correlation_trace_id = correlation_context.get("trace_id")
        correlation_span_id = correlation_context.get("span_id")
        if correlation_trace_id and correlation_span_id:
            payload["dd.trace_id"] = str(correlation_trace_id)
            payload["dd.span_id"] = str(correlation_span_id)

        return json.dumps(payload, ensure_ascii=True)


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {
            "format": "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S",
        },
        "json": {
            "()": DatadogJsonFormatter,
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if settings.log_format.lower() == "json" else "plain",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "python_multipart": {"level": "WARNING"},
        **{
            logger_name: {"level": azure_sdk_level}
            for logger_name in NOISY_DEPENDENCY_LOGGERS
        },
    },
    "root": {
        "level": level,
        "handlers": ["console"],
    },
}


def configure_logging() -> None:
    LOGGING_CONFIG["root"]["handlers"] = ["console"]
    logging.config.dictConfig(LOGGING_CONFIG)
    logging.getLogger("ddtrace").setLevel(settings.ddtrace_log_level.upper())

    if tracer is not None and _DropConnectionOpsFilter is not None:
        tracer.configure(trace_processors=[_DropConnectionOpsFilter()])

    # Chonkie emits a non-actionable tokenizer fallback warning on each invocation.
    warnings.filterwarnings(
        "ignore",
        message=r"Could not load tokenizer with 'tokenizers'\. Falling back to 'tiktoken'\.",
        category=UserWarning,
        module=r"chonkie\.tokenizer",
    )

    # Azure Search generated models can emit noisy SyntaxWarning entries in py3.12.
    warnings.filterwarnings(
        "ignore",
        category=SyntaxWarning,
        module=r"azure\.search\.documents\.indexes\._generated\.models\._models_py3",
    )

    for logger_name in NOISY_DEPENDENCY_LOGGERS:
        logging.getLogger(logger_name).setLevel(azure_sdk_level)
