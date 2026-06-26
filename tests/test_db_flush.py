"""Tests for db.flush_events failure path (Wave 1 fix #4: re-entrant lock deadlock)."""
import pytest
import asyncio
from datetime import datetime
from uuid import uuid4

from tracea.server.models import TracedEvent
from tracea.server import db as dbmod


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    db_file = tmp_path / "tracea_test.db"
    monkeypatch.setattr("tracea.server.db.DB_PATH", str(db_file))
    monkeypatch.setattr("tracea.server.db._db", None)
    dbmod._write_buffer.clear()  # reset module-level buffer between tests
    asyncio.run(dbmod.init_db())
    yield
    asyncio.run(dbmod.close_db())


def _make_event() -> TracedEvent:
    return TracedEvent(
        event_id=str(uuid4()),
        session_id=str(uuid4()),
        agent_id="test",
        sequence=1,
        timestamp=datetime.utcnow(),
        type="chat.completion",
        provider="openai",
        model="gpt-4o",
        content="x",
    )


async def _enqueue(event: TracedEvent) -> None:
    """Put an event into the write buffer using the real conversion path."""
    await dbmod.enqueue_events([event])


def test_flush_events_write_failure_does_not_deadlock(monkeypatch):
    """Regression: a failure inside the flush transaction must NOT deadlock.

    Previously the except block re-acquired _write_lock (already held by the
    same task), and since asyncio.Lock is non-reentrant, ingest hung forever.
    With the fix the failure raises promptly and events are restored to the
    buffer. asyncio.wait_for asserts the call returns within a timeout.
    """
    # Seed the write buffer with an event via the real conversion path
    asyncio.run(_enqueue(_make_event()))
    assert len(dbmod._write_buffer) == 1

    # Force the batch INSERT to fail
    real_db = dbmod._db

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated write failure")

    monkeypatch.setattr(real_db, "executemany", _boom)

    # Must raise (not hang). wait_for converts a hang into a TimeoutError.
    with pytest.raises(RuntimeError, match="simulated write failure"):
        asyncio.run(asyncio.wait_for(dbmod.flush_events(), timeout=5.0))

    # Event must be restored to the buffer on failure
    assert len(dbmod._write_buffer) == 1, "event should be restored after write failure"

    # The lock must be releasable now (proves it's not held — no deadlock)
    async def _acquire_release():
        async with dbmod._write_lock:
            pass

    asyncio.run(asyncio.wait_for(_acquire_release(), timeout=5.0))


def test_flush_events_succeeds_after_recovery(monkeypatch):
    """After a failed flush, a subsequent successful flush works normally."""
    asyncio.run(_enqueue(_make_event()))

    call_count = {"n": 0}
    real_executemany = dbmod._db.executemany

    async def _flaky(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("transient failure")
        return await real_executemany(*args, **kwargs)

    monkeypatch.setattr(dbmod._db, "executemany", _flaky)

    # First flush fails
    with pytest.raises(RuntimeError):
        asyncio.run(asyncio.wait_for(dbmod.flush_events(), timeout=5.0))

    assert len(dbmod._write_buffer) == 1

    # Second flush succeeds (lock was released, no deadlock state)
    flushed = asyncio.run(asyncio.wait_for(dbmod.flush_events(), timeout=5.0))
    assert flushed == 1
    assert len(dbmod._write_buffer) == 0
