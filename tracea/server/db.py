import os
import sqlite3
import aiosqlite
import asyncio
import json
from pathlib import Path
from typing import AsyncGenerator
import fcntl
from tracea.server.models import TracedEvent

DB_PATH = os.getenv("TRACEA_DB_PATH", "/data/tracea.db")
MIGRATIONS_DIR = Path(__file__).parent / "migrations"

_db: aiosqlite.Connection | None = None
_checkpoint_task: asyncio.Task | None = None

# --- Startup checks ---


def check_sqlite_version() -> None:
    """Fail fast if SQLite version is vulnerable to WAL corruption bug."""
    version = sqlite3.sqlite_version
    if version < "3.51.3":
        raise RuntimeError(
            f"SQLite {version} is vulnerable to WAL corruption (fixed in 3.51.3). "
            f"Upgrade SQLite or use a different Docker base image."
        )
    print(f"[tracea] SQLite version: {version}")


def check_posix_locking(data_dir: str = "/data") -> bool:
    """Test if /data supports POSIX advisory locking. Warn if NFS/EFS detected."""
    lock_file = Path(data_dir) / ".tracea_lock_test"
    try:
        with open(lock_file, "w") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            lock_file.unlink()
        return True
    except (IOError, OSError):
        print("[tracea] WARNING: /data does not support POSIX advisory locking.")
        print("[tracea] WARNING: This may indicate NFS/EFS. SQLite WAL can corrupt on network filesystems.")
        return False


# --- Database connection ---


async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    global _db
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    yield _db


async def init_db() -> aiosqlite.Connection:
    """Initialize database connection with WAL mode and correct pragmas."""
    global _db
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    check_sqlite_version()
    check_posix_locking(os.path.dirname(DB_PATH))

    _db = await aiosqlite.connect(DB_PATH, isolation_level=None)
    _db.row_factory = aiosqlite.Row

    # WAL mode + performance pragmas
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA synchronous=NORMAL")
    await _db.execute("PRAGMA busy_timeout=5000")
    await _db.execute("PRAGMA cache_size=-64000")
    await _db.execute("PRAGMA temp_store=MEMORY")

    await _db.execute("PRAGMA wal_autocheckpoint=0")  # We manage checkpoints manually

    await apply_migrations(_db)

    # Start background WAL checkpoint task
    _start_checkpoint_task()

    print(f"[tracea] Database initialized at {DB_PATH}")
    return _db


async def apply_migrations(db: aiosqlite.Connection) -> None:
    """Apply numbered SQL migration files in order."""
    # Ensure migrations table exists
    await db.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # Get already-applied migrations
    cursor = await db.execute("SELECT version FROM schema_migrations")
    applied = {row[0] for row in await cursor.fetchall()}

    # Find and apply pending migrations
    migration_files = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))
    for migration_file in migration_files:
        version = migration_file.stem  # e.g., "001_initial"
        if version in applied:
            continue
        print(f"[tracea] Applying migration: {version}")
        sql = migration_file.read_text()
        await db.executescript(sql)
        await db.execute(
            "INSERT INTO schema_migrations (version) VALUES (?)",
            (version,)
        )
        await db.commit()
        print(f"[tracea] Migration {version} applied.")


# --- WAL checkpoint background task ---


def _start_checkpoint_task() -> None:
    global _checkpoint_task
    _checkpoint_task = asyncio.create_task(_wal_checkpoint_loop())


async def _wal_checkpoint_loop() -> None:
    """Run PRAGMA wal_checkpoint(TRUNCATE) every 60 seconds."""
    while True:
        await asyncio.sleep(60)
        try:
            if _db:
                await _db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                print("[tracea] WAL checkpoint completed")
        except Exception as e:
            print(f"[tracea] WAL checkpoint failed: {e}")


# --- Batch writer ---


_write_buffer: list[tuple] = []
_write_lock = asyncio.Lock()
_flush_timer: asyncio.Task | None = None
_FLUSH_EVENTS = 100
_FLUSH_MS = 500


def _start_flush_timer() -> None:
    global _flush_timer
    if _flush_timer is None:
        _flush_timer = asyncio.create_task(_flush_loop())


async def _flush_loop() -> None:
    """Background timer: flush buffer every FLUSH_MS milliseconds."""
    while True:
        await asyncio.sleep(_FLUSH_MS / 1000.0)
        await flush_events()


async def enqueue_events(events: list[TracedEvent]) -> None:
    """Add events to write buffer. Triggers flush at 100 events or timer."""
    global _write_buffer
    for event in events:
        tokens = event.tokens_used
        _write_buffer.append((
            str(event.event_id),
            str(event.session_id),
            event.agent_id,
            event.sequence,
            event.timestamp.isoformat(),
            "1",  # schema_version
            event.type,
            event.provider,
            event.model,
            event.role or "",
            event.content or "",
            event.tool_call_id or "",
            event.tool_name or "",
            str(event.status_code or ""),
            event.error or "",
            event.duration_ms,
            str(tokens.input if tokens else 0) if tokens else "0",
            str(tokens.output if tokens else 0) if tokens else "0",
            str(tokens.total if tokens else 0) if tokens else "0",
            str(event.cost_usd or ""),
            json.dumps(event.metadata),
        ))
        # Check if we need to flush
        if len(_write_buffer) >= _FLUSH_EVENTS:
            await flush_events()

    # Start flush timer if not running
    if _flush_timer is None:
        _start_flush_timer()


async def flush_events() -> int:
    """Flush buffered events to SQLite. Returns number of events flushed."""
    global _write_buffer
    if not _write_buffer:
        return 0

    async with _write_lock:
        batch = list(_write_buffer)
        _write_buffer.clear()

    if not batch:
        return 0

    if _db is None:
        raise RuntimeError("Database not initialized")

    # Use BEGIN IMMEDIATE to avoid lock escalation
    await _db.execute("BEGIN IMMEDIATE")
    try:
        await _db.executemany(
            """INSERT OR REPLACE INTO events
            (event_id, session_id, agent_id, sequence, timestamp, schema_version,
             type, provider, model, role, content, tool_call_id, tool_name,
             status_code, error, duration_ms, input_tokens, output_tokens,
             total_tokens, cost_usd, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            batch
        )
        await _db.commit()
    except Exception:
        await _db.rollback()
        # Put events back in buffer on failure
        _write_buffer = batch + _write_buffer
        raise

    return len(batch)


async def run_wal_checkpoint() -> None:
    """Run a WAL checkpoint manually. Useful for testing and graceful shutdown."""
    if _db:
        await _db.execute("PRAGMA wal_checkpoint(TRUNCATE)")


async def close_db() -> None:
    global _db, _checkpoint_task, _flush_timer
    if _flush_timer:
        _flush_timer.cancel()
    if _checkpoint_task:
        _checkpoint_task.cancel()
    if _db:
        await _db.close()
        _db = None
