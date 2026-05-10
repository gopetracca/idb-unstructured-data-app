import importlib
import json
import logging

import src.utils.base_logger as base_logger
from src.config import settings as settings_module


def _reload_base_logger():
    settings_module.reload_settings()
    return importlib.reload(base_logger)


def test_configure_logging_streams_to_console(monkeypatch):
    monkeypatch.setenv("DD_LOGS_ENABLED", "true")

    logger_module = _reload_base_logger()

    logger_module.configure_logging()

    assert logger_module.LOGGING_CONFIG["root"]["handlers"] == ["console"]
    assert "file" not in logger_module.LOGGING_CONFIG["handlers"]


def test_configure_logging_has_no_file_handler():
    logger_module = _reload_base_logger()

    logger_module.configure_logging()

    assert logger_module.LOGGING_CONFIG["root"]["handlers"] == ["console"]
    assert "file" not in logger_module.LOGGING_CONFIG["handlers"]


def test_configure_logging_suppresses_azure_sdk_http_chatter():
    logger_module = _reload_base_logger()

    logger_module.configure_logging()

    assert logging.getLogger("azure.core.pipeline.policies.http_logging_policy").level == logging.WARNING
    assert logging.getLogger("azure.storage.blob").level == logging.WARNING
    assert logging.getLogger("azure.search").level == logging.WARNING
    assert logging.getLogger("azure_functions_worker").level == logging.WARNING


def test_configure_logging_registers_chonkie_tokenizer_warning_filter(monkeypatch):
    logger_module = _reload_base_logger()
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def _capture_filterwarnings(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(logger_module.warnings, "filterwarnings", _capture_filterwarnings)

    logger_module.configure_logging()

    assert len(calls) >= 2

    args, kwargs = calls[0]
    assert args[0] == "ignore"
    assert "Could not load tokenizer with 'tokenizers'" in str(kwargs["message"])
    assert kwargs["category"] is UserWarning
    assert kwargs["module"] == r"chonkie\.tokenizer"

    args, kwargs = calls[1]
    assert args[0] == "ignore"
    assert kwargs["category"] is SyntaxWarning
    assert kwargs["module"] == r"azure\.search\.documents\.indexes\._generated\.models\._models_py3"


def test_datadog_json_formatter_keeps_message_on_one_physical_line():
    formatter = base_logger.DatadogJsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Request URL: 'https://example'\nRequest method: 'PUT'",
        args=(),
        exc_info=None,
    )

    output = formatter.format(record)

    assert "\n" not in output
    payload = json.loads(output)
    assert payload["message"] == "Request URL: 'https://example'\\nRequest method: 'PUT'"
