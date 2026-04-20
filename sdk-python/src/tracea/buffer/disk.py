"""DiskBuffer — aiosqlite append-only persistence for tracea events.

Events are written to SQLite when the server is unreachable.
On reconnect, events are replayed to the server and deleted from disk.

Schema:
    events (
        event_id TEXT PRIMARY KEY,  -- dedup on replay
        session_id TEXT NOT NULL,
        agent_id TEXT,
        sequence INTEGER,
        timestamp TEXT,
        type TEXT,
        provider TEXT,
        model TEXT,
        role TEXT,
        content TEXT,
        tool_call_id TEXT,
        tool_name TEXT,
        status_code INTEGER,
        error TEXT,
        duration_ms INTEGER,
        tokens_used_json TEXT,  -- JSON serialized
        cost_usd REAL,
        metadata_json TEXT,     -- JSON serialized
        raw_json TEXT            -- full event as JSON
    )
"""
from __future__ import annotations
import asyncio
import aiosqlite
import json
import os
import logging
from pathlib import Path
from typing import Callable, Awaitable
from tracea.events import TracedEvent

logger = logging.getLogger("tracea.disk_buffer")

class DiskBuffer:
    DEFAULT_DB_PATH = os.path.expanduser("~/.tracea/buffer.db")

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or self.DEFAULT_DB_PATH
        self._db: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def _get_db(self) -> aiosqlite.Connection:
        if self._db is None:
            # Ensure directory exists
            db_dir = os.path.dirname(self._db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
            self._db = await aiosqlite.connect(self._db_path)
            self._db.row_factory = aiosqlite.Row
            await self._db.execute("PRAGMA journal_mode=WAL")
            await self._db.execute("PRAGMA synchronous=NORMAL")
            await self.init_db()
        return self._db

    async def init_db(self) -> None:
        db = await self._get_db()
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                agent_id TEXT,
                sequence INTEGER,
                timestamp TEXT,
                type TEXT,
                provider TEXT,
                model TEXT,
                role TEXT,
                content TEXT,
                tool_call_id TEXT,
                tool_name TEXT,
                status_code INTEGER,
                error TEXT,
                duration_ms INTEGER,
                tokens_used_json TEXT,
                cost_usd REAL,
                metadata_json TEXT,
                raw_json TEXT
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_session_id ON events(session_id)
        """)
        await db.commit()

    def _event_to_row(self, event: TracedEvent) -> dict:
        """Serialize a TracedEvent to a DB row dict."""
        return {
            "event_id": str(event.event_id),
            "session_id": str(event.session_id),
            "agent_id": event.agent_id,
            "sequence": event.sequence,
            "timestamp": event.timestamp.isoformat() if hasattr(event.timestamp, 'isoformat') else str(event.timestamp),
            "type": event.type,
            "provider": event.provider,
            "model": event.model,
            "role": event.role,
            "content": event.content,
            "tool_call_id": event.tool_call_id,
            "tool_name": event.tool_name,
            "status_code": event.status_code,
            "error": event.error,
            "duration_ms": event.duration_ms,
            "tokens_used_json": json.dumps(event.tokens_used.__dict__) if event.tokens_used else None,
            "cost_usd": event.cost_usd,
            "metadata_json": json.dumps(event.metadata),
            "raw_json": json.dumps(event.__dict__),
        }

    async def write(self, event: TracedEvent) -> None:
        """Write a single event to disk. Idempotent (INSERT OR IGNORE for dedup)."""
        async with self._lock:
            db = await self._get_db()
            row = self._event_to_row(event)
            await db.execute("""
                INSERT OR IGNORE INTO events VALUES (
                    :event_id, :session_id, :agent_id, :sequence, :timestamp,
                    :type, :provider, :model, :role, :content,
                    :tool_call_id, :tool_name, :status_code, :error, :duration_ms,
                    :tokens_used_json, :cost_usd, :metadata_json, :raw_json
                )
            """, row)
            await db.commit()

    async def write_batch(self, events: list[TracedEvent]) -> None:
        """Write multiple events in a single transaction."""
        async with self._lock:
            db = await self._get_db()
            rows = [self._event_to_row(e) for e in events]
            await db.executemany("""
                INSERT OR IGNORE INTO events VALUES (
                    :event_id, :session_id, :agent_id, :sequence, :timestamp,
                    :type, :provider, :model, :role, :content,
                    :tool_call_id, :tool_name, :status_code, :error, :duration_ms,
                    :tokens_used_json, :cost_usd, :metadata_json, :raw_json
                )
            """, rows)
            await db.commit()

    async def drain(self, flush_fn: Callable[[list[TracedEvent]], Awaitable[int]]) -> int:
        """Replay buffered events to the server via flush_fn.

        Events are replayed in chunks of 100 with cooperative yields between chunks.
        Returns the total number of events successfully flushed.

        IMPORTANT: flush_fn must be an async callable that accepts a list of TracedEvents
        and returns the number of events successfully flushed (int). This is different from
        a sync lambda because drain() awaits flush_fn directly.
        """
        async with self._lock:
            db = await self._get_db()
            flushed_total = 0
            chunk_size = 100

            while True:
                rows = await db.fetchall("""
                    SELECT * FROM events ORDER BY timestamp ASC LIMIT ?
                """, (chunk_size,))
                if not rows:
                    break

                # Convert rows to TracedEvents
                events = [self._row_to_event(row) for row in rows]
                event_ids = [str(e.event_id) for e in events]

                try:
                    # flush_fn is an async callable — await it directly
                    flushed = await flush_fn(events)
                    if flushed >= len(events):
                        # Success — delete flushed events
                        placeholders = ",".join("?" * len(event_ids))
                        await db.execute(f"""
                            DELETE FROM events WHERE event_id IN ({placeholders})
                        """, event_ids)
                        await db.commit()
                        flushed_total += flushed
                    else:
                        # Partial success — try again next cycle
                        break
                except Exception as exc:
                    logger.warning(f"DiskBuffer drain failed: {exc}")
                    break

                # Cooperative yield to allow other coroutines to run
                await asyncio.sleep(0)

            return flushed_total

    def _row_to_event(self, row: aiosqlite.Row) -> TracedEvent:
        """Convert a DB row back to a TracedEvent."""
        from tracea.events import TokenUsage
        from datetime import datetime
        from uuid import UUID

        tokens_used = None
        if row["tokens_used_json"]:
            tu_data = json.loads(row["tokens_used_json"])
            tokens_used = TokenUsage(**tu_data)

        return TracedEvent(
            event_id=UUID(row["event_id"]),
            session_id=UUID(row["session_id"]),
            agent_id=row["agent_id"] or "",
            sequence=row["sequence"] or 0,
            timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else datetime.utcnow(),
            type=row["type"],
            provider=row["provider"],
            model=row["model"] or "",
            role=row["role"],
            content=row["content"],
            tool_call_id=row["tool_call_id"],
            tool_name=row["tool_name"],
            status_code=row["status_code"],
            error=row["error"],
            duration_ms=row["duration_ms"] or 0,
            tokens_used=tokens_used,
            cost_usd=row["cost_usd"],
            metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
        )

    async def count(self) -> int:
        """Return total number of events in the buffer."""
        db = await self._get_db()
        cursor = await db.execute("SELECT COUNT(*) FROM events")
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def close(self) -> None:
        """Close the database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None
