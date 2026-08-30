"""Deprecated import path for the extraction port.

The port is named :class:`~src.application.ports.document_extractor.DocumentExtractorPort`
and lives beside this module. This shim exists so that callers written against the old
name — and work in flight against it — keep importing successfully; new code should import
from ``src.application.ports.document_extractor``.
"""

from src.application.ports.document_extractor import (
    DocumentExtractorPort,
    DocumentIntelligencePort,
)

__all__ = ["DocumentExtractorPort", "DocumentIntelligencePort"]
