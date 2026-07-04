"""Request body size limiting (AIA-478).

Layered defense for uploads on a memory-capped Container App:

1. ``Content-Length`` pre-check — rejects well-behaved oversized clients with
   413 before a single body byte is read.
2. Streaming byte counter — ``Content-Length`` can be absent (chunked) or
   understated, so the wrapped ``receive`` also counts actual bytes and aborts
   the moment the running total exceeds the limit. The raised
   ``FileSizeExceededError`` is converted to a 413 by the registered exception
   handler, and Starlette's multipart parser spools to disk past 1 MB, so peak
   RAM stays bounded regardless of the declared or real body size.
"""

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.core.errors import FileSizeExceededError

# Multipart framing, boundary lines, and form fields ride along with the file
# bytes, so the request-level limit needs headroom above the file-size limit.
MULTIPART_OVERHEAD_BYTES = 1024 * 1024


class MaxBodySizeMiddleware:
    """Reject request bodies larger than ``max_file_size_bytes`` + overhead with 413."""

    def __init__(self, app: ASGIApp, max_file_size_bytes: int) -> None:
        self.app = app
        self.max_body_size_bytes = max_file_size_bytes + MULTIPART_OVERHEAD_BYTES

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = self._declared_content_length(scope)
        if declared is not None and declared > self.max_body_size_bytes:
            response = self._too_large_response(declared)
            await response(scope, receive, send)
            return

        received_total = 0

        async def limited_receive() -> Message:
            nonlocal received_total
            message = await receive()
            if message["type"] == "http.request":
                received_total += len(message.get("body", b""))
                if received_total > self.max_body_size_bytes:
                    # Converted to a 413 by the FileSizeExceededError handler.
                    raise FileSizeExceededError(received_total, self.max_body_size_bytes)
            return message

        await self.app(scope, limited_receive, send)

    def _declared_content_length(self, scope: Scope) -> int | None:
        raw = Headers(scope=scope).get("content-length")
        if raw is None:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    def _too_large_response(self, declared: int) -> JSONResponse:
        return JSONResponse(
            status_code=413,
            content={
                "error": "FileSizeExceeded",
                "message": "Request body exceeds the maximum allowed size",
                "details": {
                    "size_bytes": declared,
                    "max_size_bytes": self.max_body_size_bytes,
                },
            },
        )
