"""BatchBuffer — asyncio-native event batching for tracea SDK.

Batches events in memory and flushes on max(50 events, 1 second).
Overflows to DiskBuffer when the server is unreachable.
Drains DiskBuffer on reconnect before new events go directly to the server.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Callable, Awaitable
from tracea.events import TracedEvent
from tracea.buffer.disk import DiskBuffer
from tracea.api import TraceaAPIClient

logger = logging.getLogger("tracea.batch_buffer")

# Retry backoff: 1s, 2s, 4s, 8s, cap 30s
RETRY_BACKOFF_SECS = [1, 2, 4, 8, 16, 30]
MAX_BATCH_SIZE = 50
FLUSH_TIMEOUT_SECS = 1.0

class BatchBuffer:
    def __init__(
        self,
        api_client: TraceaAPIClient,
        disk_buffer: DiskBuffer | None = None,
    ):
        self._events: list[TracedEvent] = []
        self._lock = asyncio.Lock()
        self._timer_task: asyncio.Task | None = None
        self._api_client = api_client
        self._disk_buffer = disk_buffer or DiskBuffer()
        self._draining = False
        self._retry_backoff_index = 0

    async def add(self, event: TracedEvent) -> None:
        """Add an event to the batch. Flushes automatically on size or time threshold."""
        async with self._lock:
            self._events.append(event)
            should_flush = len(self._events) >= MAX_BATCH_SIZE

            # Schedule timer on first event
            if self._timer_task is None:
                self._timer_task = asyncio.create_task(self._flush_after(FLUSH_TIMEOUT_SECS))

            if should_flush:
                await self._flush()

    async def _flush_after(self, delay: float) -> None:
        """Timer-based flush after delay seconds."""
        await asyncio.sleep(delay)
        async with self._lock:
            if self._events:
                await self._flush()
            self._timer_task = None

    async def _flush(self) -> None:
        """Flush the current batch to the server. Called with lock held."""
        if not self._events:
            return

        batch = self._events[:]
        self._events.clear()
        self._timer_task = None

        success = await self._try_flush(batch)

        if not success:
            # Server unreachable — overflow to DiskBuffer
            await self._disk_buffer.write_batch(batch)
            logger.debug(f"BatchBuffer overflow: {len(batch)} events written to DiskBuffer")

    async def _try_flush(self, batch: list[TracedEvent]) -> bool:
        """Attempt to flush batch to server.

        Returns True on success, False on failure (connection error or 5xx).
        On 4xx: returns True (don't buffer — client error won't succeed on retry).
        """
        try:
            accepted = await self._api_client.post_events(batch)
            self._retry_backoff_index = 0  # Reset backoff on success
            logger.debug(f"BatchBuffer flushed {accepted} events")
            return accepted >= len(batch)
        except ConnectionError:
            return False
        except Exception as exc:
            if hasattr(exc, "response") and hasattr(exc.response, "status_code"):
                status = exc.response.status_code
                if 400 <= status < 500:
                    # 4xx — don't buffer, client error won't succeed on retry
                    logger.warning(f"BatchBuffer: server rejected batch with {status}, not buffering")
                    return True
                if status >= 500:
                    # 5xx — buffer for retry
                    return False
            return False

    async def _flush_batch(self, events: list[TracedEvent]) -> int:
        """Async method to flush a batch of events to the server.

        Used by drain_disk_buffer() to pass to DiskBuffer.drain().
        This is an async method (not a lambda) so it can be awaited directly.
        """
        return await self._api_client.post_events(events)

    async def drain_disk_buffer(self) -> int:
        """Drain the DiskBuffer to the server.

        DiskBuffer is drained BEFORE new events go directly to the server.
        Events are replayed in chunks until DiskBuffer is empty.
        Returns total events flushed.
        """
        if self._draining:
            return 0

        self._draining = True
        total_flushed = 0

        try:
            while True:
                count = await self._disk_buffer.count()
                if count == 0:
                    break

                # IMPORTANT: Use self._flush_batch (async method), NOT a lambda.
                # A sync lambda returning a coroutine cannot be awaited directly.
                # DiskBuffer.drain() awaits flush_fn, so flush_fn must be an awaitable.
                flushed = await self._disk_buffer.drain(self._flush_batch)
                if flushed == 0:
                    # No progress — apply backoff before retry
                    backoff = RETRY_BACKOFF_SECS[
                        min(self._retry_backoff_index, len(RETRY_BACKOFF_SECS) - 1)
                    ]
                    self._retry_backoff_index += 1
                    logger.debug(f"DiskBuffer drain: no progress, retrying in {backoff}s")
                    await asyncio.sleep(backoff)
                else:
                    total_flushed += flushed
                    self._retry_backoff_index = 0  # Reset backoff on progress

        finally:
            self._draining = False

        return total_flushed

    async def flush_now(self) -> None:
        """Force an immediate flush. Used on shutdown."""
        async with self._lock:
            if self._events:
                await self._flush()

    async def close(self) -> None:
        """Close the buffer, flushing any remaining events."""
        await self.flush_now()
        if self._timer_task:
            self._timer_task.cancel()
            try:
                await self._timer_task
            except asyncio.CancelledError:
                pass
        await self._disk_buffer.close()
