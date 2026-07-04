"""Bounded reading of multipart uploads (AIA-478).

Authoritative size guard at the route level: reads the ``UploadFile`` in fixed
chunks and aborts with ``FileSizeExceededError`` (→ 413) the moment the running
total crosses the configured limit, instead of buffering the whole body and
checking afterwards. Starlette already spools uploads larger than 1 MB to disk,
so the read itself never holds more than one chunk in RAM; the payload is only
materialized as ``bytes`` once it is known to be within the limit (the upload
use case currently takes ``bytes``).
"""

from fastapi import UploadFile

from src.core.errors import FileSizeExceededError

_CHUNK_SIZE_BYTES = 1024 * 1024


async def read_upload_bounded(file: UploadFile, max_size_bytes: int) -> bytes:
    """Read ``file`` fully, raising ``FileSizeExceededError`` past ``max_size_bytes``."""
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_CHUNK_SIZE_BYTES):
        total += len(chunk)
        if total > max_size_bytes:
            raise FileSizeExceededError(total, max_size_bytes)
        chunks.append(chunk)
    return b"".join(chunks)
