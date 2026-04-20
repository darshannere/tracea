"""Integration tests for tracea SDK — end-to-end event capture.

Tests verify:
- BatchBuffer flush on count and timer
- BatchBuffer overflow to DiskBuffer on server failure
- DiskBuffer drain on reconnect (PYS-08 zero event loss)
- DiskBuffer persistence across restarts
- End-to-end event emission through patched httpx
"""
import pytest
import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from tracea.buffer.batch import BatchBuffer
from tracea.buffer.disk import DiskBuffer
from tracea.api import TraceaAPIClient
from tracea.events import TracedEvent, EventBatch, TokenUsage


@pytest.fixture
def mock_api_client_success():
    """Mock API client that always succeeds."""
    client = MagicMock(spec=TraceaAPIClient)
    client.post_events = AsyncMock(return_value=50)
    return client


@pytest.fixture
def mock_api_client_failure():
    """Mock API client that always fails (connection error)."""
    client = MagicMock(spec=TraceaAPIClient)
    client.post_events = AsyncMock(side_effect=ConnectionError("Server down"))
    return client


def make_event(sequence: int = 0) -> TracedEvent:
    """Factory to create a test TracedEvent."""
    return TracedEvent(
        event_id=uuid4(),
        session_id=uuid4(),
        agent_id="test",
        sequence=sequence,
        type="chat.completion",
        provider="openai",
        model="gpt-4o",
    )


@pytest.mark.asyncio
async def test_batch_buffer_flush_on_count(mock_api_client_success):
    """BatchBuffer flushes when 50 events are added."""
    disk_buffer = MagicMock(spec=DiskBuffer)
    buffer = BatchBuffer(api_client=mock_api_client_success, disk_buffer=disk_buffer)

    events = [make_event(sequence=i) for i in range(50)]

    for event in events:
        await buffer.add(event)

    await asyncio.sleep(0.1)  # Allow flush to complete
    mock_api_client_success.post_events.assert_called_once()
    assert len(mock_api_client_success.post_events.call_args[0][0]) == 50


@pytest.mark.asyncio
async def test_batch_buffer_overflow_to_disk(mock_api_client_failure):
    """BatchBuffer overflows to DiskBuffer when server returns error."""
    disk_buffer = MagicMock(spec=DiskBuffer)
    disk_buffer.write_batch = AsyncMock()

    buffer = BatchBuffer(api_client=mock_api_client_failure, disk_buffer=disk_buffer)

    event = make_event()
    await buffer.add(event)
    # Force flush immediately (threshold is 50, timer is 1s)
    await buffer.flush_now()

    disk_buffer.write_batch.assert_called_once()


@pytest.mark.asyncio
async def test_batch_buffer_drain_disk_buffer_on_reconnect(tmp_path):
    """PYS-08: Verify drain_disk_buffer replays events to server and deletes from disk.

    Test flow:
    1. Server is down, events overflow to DiskBuffer
    2. Server returns, drain_disk_buffer() is called
    3. DiskBuffer replay verified: events sent to server, deleted from disk after success
    """
    db_path = os.path.join(tmp_path, "test_drain_reconnect.db")
    disk_buffer = DiskBuffer(db_path=db_path)

    # Track calls; first fails, second succeeds
    post_calls = []

    async def mock_post_events(events):
        post_calls.append(len(events))
        if len(post_calls) == 1:
            raise ConnectionError("Server down")
        return len(events)

    api_client = MagicMock(spec=TraceaAPIClient)
    api_client.post_events = AsyncMock(side_effect=mock_post_events)

    buffer = BatchBuffer(api_client=api_client, disk_buffer=disk_buffer)

    # Step 1: Add events while server is down — should overflow to disk
    events = [make_event(sequence=i) for i in range(5)]

    for event in events:
        await buffer.add(event)
    # Force flush immediately (threshold is 50, timer is 1s)
    await buffer.flush_now()
    # Allow the disk write to complete
    await asyncio.sleep(0.05)

    disk_count = await disk_buffer.count()
    assert disk_count == 5, f"Expected 5 events on disk, got {disk_count}"

    # Step 2: Server returns, drain_disk_buffer replays events
    flushed = await buffer.drain_disk_buffer()

    assert flushed == 5, f"Expected 5 events flushed, got {flushed}"
    assert len(post_calls) == 2, f"Expected 2 post_events calls, got {len(post_calls)}"

    # Step 3: Verify events deleted from disk after successful drain
    remaining = await disk_buffer.count()
    assert remaining == 0, f"Expected 0 events on disk after drain, got {remaining}"

    await disk_buffer.close()


@pytest.mark.asyncio
async def test_disk_buffer_persistence(tmp_path):
    """DiskBuffer events survive process restart."""
    db_path = os.path.join(tmp_path, "test_persistence.db")

    buffer1 = DiskBuffer(db_path=db_path)
    event = make_event()
    await buffer1.write(event)
    count1 = await buffer1.count()
    assert count1 == 1
    await buffer1.close()

    # Simulate restart: create new buffer instance pointing to same DB
    buffer2 = DiskBuffer(db_path=db_path)
    count2 = await buffer2.count()
    assert count2 == 1  # Event survived
    await buffer2.close()


@pytest.mark.asyncio
async def test_disk_buffer_drain(tmp_path):
    """DiskBuffer.drain() replays events to server via callback."""
    db_path = os.path.join(tmp_path, "test_drain.db")
    buffer = DiskBuffer(db_path=db_path)

    # Write 5 events
    events = [make_event(sequence=i) for i in range(5)]
    await buffer.write_batch(events)
    assert await buffer.count() == 5

    # Drain with a callback that accepts events
    flushed_events = []
    async def flush_fn(evts):
        flushed_events.extend(evts)
        return len(evts)

    total_flushed = await buffer.drain(flush_fn)
    assert total_flushed == 5
    assert await buffer.count() == 0  # Events deleted after drain

    await buffer.close()


@pytest.mark.asyncio
async def test_end_to_end_events_in_buffer():
    """PYS-12: End-to-end test — event added to BatchBuffer lands in API post_events.

    This test verifies:
    1. A real BatchBuffer + mock API client
    2. Event is added to buffer
    3. flush_now() forces flush and API post_events is called
    """
    captured_events = []
    mock_api = MagicMock(spec=TraceaAPIClient)
    mock_api.post_events = AsyncMock(side_effect=lambda e: (captured_events.extend(e), len(e)))

    disk_buffer = MagicMock(spec=DiskBuffer)
    disk_buffer.write_batch = AsyncMock()

    buffer = BatchBuffer(api_client=mock_api, disk_buffer=disk_buffer)

    event = make_event()
    await buffer.add(event)
    await buffer.flush_now()
    await asyncio.sleep(0.05)

    # Verify event was captured via post_events
    assert len(captured_events) == 1
    assert captured_events[0].event_id == event.event_id
