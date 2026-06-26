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


def test_foreign_key_cascade_delete_works():
    """Regression: PRAGMA foreign_keys=ON must be set so ON DELETE CASCADE fires.

    Without the pragma, FK declarations are no-ops and deleting a parent row
    leaves orphaned children. Verify via api_keys → users cascade.
    """
    import aiosqlite

    async def _run():
        db = dbmod._db
        # Insert a user + a child api_key row
        await db.execute(
            "INSERT INTO users (user_id, name, email) VALUES (?, ?, ?)",
            ("cascade-user", "Cascade", "c@example.com"),
        )
        await db.execute(
            "INSERT INTO api_keys (key_hash, user_id) VALUES (?, ?)",
            ("hash", "cascade-user"),
        )
        await db.commit()

        # Confirm FK enforcement is actually on for this connection
        cursor = await db.execute("PRAGMA foreign_keys")
        row = await cursor.fetchone()
        assert row[0] == 1, f"foreign_keys pragma must be ON, got {row[0]}"

        # Delete the parent — child must cascade-delete
        await db.execute("DELETE FROM users WHERE user_id = ?", ("cascade-user",))
        await db.commit()

        cur_key = await db.execute("SELECT COUNT(*) FROM api_keys WHERE user_id = ?", ("cascade-user",))
        count = (await cur_key.fetchone())[0]
        assert count == 0, "api_keys row should have been cascade-deleted"

    asyncio.run(_run())


def test_migration_numbers_are_unique():
    """Regression: migration filename prefixes (NNN_) must be unique.

    Two migrations shared the 011 prefix (011_add_api_keys_table and
    011_add_settings_table), which makes ordering ambiguous and risks
    shadowing. assert no two files share a prefix."""
    from pathlib import Path

    migrations_dir = Path(dbmod.__file__).parent / "migrations"
    files = sorted(migrations_dir.glob("[0-9][0-9][0-9]_*.sql"))
    prefixes = [f.name[:3] for f in files]
    assert len(prefixes) == len(set(prefixes)), (
        f"Duplicate migration prefixes: {prefixes}"
    )
    # Sanity: the settings migration is now 013, not a second 011
    assert not (migrations_dir / "011_add_settings_table.sql").exists()
    assert (migrations_dir / "013_add_settings_table.sql").exists()
