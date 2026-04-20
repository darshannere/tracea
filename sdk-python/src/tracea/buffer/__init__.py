"""Tiered buffer system: BatchBuffer + DiskBuffer.

Buffer singleton wires together:
1. BatchBuffer — in-memory batching, flushes on 50 events or 1s
2. DiskBuffer — overflow persistence when server is unreachable
3. Transport patches — installed when buffer is first accessed
"""
from __future__ import annotations
from tracea.buffer.batch import BatchBuffer
from tracea.buffer.disk import DiskBuffer
from tracea.api import TraceaAPIClient
from tracea.patch.httpx import patch

_buffer: BatchBuffer | None = None

def get_buffer() -> BatchBuffer:
    """Return the singleton BatchBuffer instance.

    Initializes the buffer system on first call.
    Raises RuntimeError if tracea.init() has not been called.
    """
    global _buffer

    if _buffer is not None:
        return _buffer

    # Lazy import to avoid circular dependencies
    from tracea.config import get_config

    try:
        config = get_config()
    except RuntimeError:
        raise RuntimeError(
            "tracea.init() must be called before get_buffer(). "
            "Import tracea and call tracea.init() first."
        )

    # Install transport patches
    patch()

    # Create tiered buffer
    disk_buffer = DiskBuffer()
    api_client = TraceaAPIClient()
    _buffer = BatchBuffer(api_client=api_client, disk_buffer=disk_buffer)

    return _buffer

__all__ = ["get_buffer", "BatchBuffer", "DiskBuffer"]
