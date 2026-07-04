"""HTTP middleware."""

from src.presentation.http.middleware.max_body_size import MaxBodySizeMiddleware

__all__ = ["MaxBodySizeMiddleware"]
