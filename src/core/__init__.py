"""Core domain module containing entities and value objects."""

from src.core.errors import (
    DocumentNotFoundError,
    DocumentProcessingError,
    DomainError,
    UnsupportedFormatError,
    ValidationError,
)

__all__ = [
    "DomainError",
    "DocumentProcessingError",
    "UnsupportedFormatError",
    "DocumentNotFoundError",
    "ValidationError",
]
