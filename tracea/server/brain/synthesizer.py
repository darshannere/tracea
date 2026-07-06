"""Brain Synthesizer — background worker that turns agent sessions into knowledge.

Data flow:
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌─────────────┐
│  sessions   │────►│  fetch_events │────►│  compress   │────►│   redact    │
│brain_status │     │  (type filter)│     │  (dedup,    │     │  (secrets)  │
│  = pending  │     │               │     │  truncate,  │     │             │
└─────────────┘     └──────────────┘     │  sample)    │     └─────────────┘
                                          └──────┬──────┘            │
                                                 ▼                   │
                                          ┌─────────────┐            │
                                          │  build_prompt│◄───────────┘
                                          └──────┬──────┘
                                                 ▼
                                          ┌─────────────┐
                                          │ call_backend │  ◄── closes DB here
                                          │  (LLM call)  │     to avoid lock
                                          └──────┬──────┘
                                                 ▼
                                          ┌─────────────┐
                                          │ parse_json   │
                                          │ + validate   │
                                          │  (Pydantic)  │
                                          └──────┬──────┘
                                                 ▼
                                          ┌─────────────┐
                                          │ upsert to    │
                                          │ brain_entries│
                                          └─────────────┘
"""

import asyncio
import hashlib
import json
import logging
from typing import Any

import aiosqlite
from pydantic import TypeAdapter, ValidationError

from tracea.server.brain.models import BrainEntryExtract
from tracea.server.brain.prompts import build_brain_prompt, load_custom_prompt
from tracea.server.redaction import redact
from tracea.server.rca.backends import load_backend, RCABackend
from tracea.server.rca.models import RCABackendConfig
from tracea.server.settings import get_brain_config

logger = logging.getLogger(__name__)

from tracea.server.worker_base import PollingWorker

_POLL_INTERVAL = 5  # seconds between polls
_WORKER_MIN_EVENTS = 5  # skip sessions with fewer events after type filter
_MAX_EVENTS_FETCH = 1000  # safety cap

_worker: PollingWorker | None = None


def _compute_entry_id(category: str, title: str) -> str:
    """Stable ID for a brain entry based on category + normalized title."""
    key = f"{category}|{title.lower().strip()}"
    return hashlib.sha256(key.encode()).hexdigest()


def _compress_events(events: list[dict]) -> str:
    """Compress session events into a compact plain-text summary.

    Steps:
    1. Deduplicate consecutive identical tool_name calls
    2. Truncate tool_result content to 200 chars
    3. Keep all error events in full
    4. If > 100 events: keep first 50 + last 50, sample every Nth from middle
    """
    if not events:
        return "(no events)"

    # Step 1: deduplicate consecutive identical tool_name calls
    deduped: list[dict] = []
    for ev in events:
        if (
            deduped
            and deduped[-1].get("tool_name")
            and ev.get("tool_name") == deduped[-1]["tool_name"]
            and deduped[-1].get("type") == ev.get("type")
        ):
            deduped[-1]["_count"] = deduped[-1].get("_count", 1) + 1
        else:
            deduped.append(dict(ev))

    # Step 2 & 3: format each event, truncate content, keep errors full
    lines: list[str] = []
    for ev in deduped:
        seq = ev.get("sequence", 0)
        ev_type = ev.get("type", "")
        tool = ev.get("tool_name", "")
        err = ev.get("error", "")
        content = ev.get("content", "")
        count = ev.get("_count", 1)

        # Keep errors in full; truncate other content
        if err:
            content_preview = f"ERROR: {err}"
        elif content:
            content_preview = content[:200] + ("..." if len(content) > 200 else "")
        else:
            content_preview = ""

        tool_part = f" | tool={tool}" if tool else ""
        count_part = f" x{count}" if count > 1 else ""
        content_part = f" | {content_preview}" if content_preview else ""
        lines.append(f"seq={seq}{tool_part}{count_part}{content_part}")

    # Step 4: sampling if too many lines
    if len(lines) > 100:
        first = lines[:50]
        last = lines[-50:]
        middle = lines[50:-50]
        n = max(1, len(middle) // 50)
        sampled = middle[::n][:50]
        lines = first + ["... (sampled middle) ..."] + sampled + ["... (end) ..."] + last

    return "\n".join(lines)


async def _load_config() -> RCABackendConfig:
    """Load brain config from DB settings, falling back to env vars."""
    cfg = await get_brain_config()
    return RCABackendConfig(
        backend=cfg["backend"],
        model=cfg.get("model") or None,
        base_url=cfg.get("base_url") or None,
        prompt_path=cfg.get("prompt_path") or None,
        redact_content=True,  # brain always redacts
        max_tokens=cfg.get("max_tokens", 2048),
        api_key=cfg.get("api_key") or None,
    )


async def _fetch_pending_sessions(db) -> list[dict]:
    """Fetch up to 5 sessions pending brain synthesis."""
    cursor = await db.execute(
        "SELECT session_id, user_id FROM sessions WHERE brain_status = 'pending' "
        "ORDER BY ended_at ASC LIMIT 5"
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def _fetch_events(db, session_id: str) -> list[dict]:
    """Fetch relevant events for a session, ordered by sequence."""
    cursor = await db.execute(
        """
        SELECT type, tool_name, content, error, sequence, timestamp
        FROM events
        WHERE session_id = ? AND type IN ('tool_call', 'tool_result', 'error', 'chat.completion', 'agent_turn')
        ORDER BY sequence ASC
        LIMIT ?
        """,
        (session_id, _MAX_EVENTS_FETCH),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def _open_db() -> aiosqlite.Connection:
    """Open a fresh SQLite connection (not the singleton)."""
    from tracea.server.db import DB_PATH

    db = await aiosqlite.connect(DB_PATH, isolation_level=None)
    db.row_factory = aiosqlite.Row
    # Per-connection pragma — SQLite foreign keys are off by default and must be
    # enabled on every connection for ON DELETE CASCADE to take effect.
    await db.execute("PRAGMA foreign_keys=ON")
    await db.execute("PRAGMA busy_timeout=15000")  # match the singleton's
    return db


async def _process_session(backend: RCABackend, config: RCABackendConfig, custom_prompt: str | None, session: dict) -> None:
    """Synthesize a single session into brain entries.

    Manages its own DB connection lifecycle: opens, fetches events, closes
    before the LLM call, reopens for upsert, then closes.
    """
    session_id = session["session_id"]
    user_id = session.get("user_id", "")

    # 1. Open DB and fetch events
    db = await _open_db()
    try:
        events = await _fetch_events(db, session_id)

        # 2. Noise filter
        if len(events) < _WORKER_MIN_EVENTS:
            logger.info(f"[brain] Session {session_id} has {len(events)} events (< {_WORKER_MIN_EVENTS}), skipping")
            await db.execute(
                "UPDATE sessions SET brain_status = 'done' WHERE session_id = ?",
                (session_id,),
            )
            await db.commit()
            return
    finally:
        await db.close()

    try:
        # 3. Compress and redact
        summary = _compress_events(events)
        summary = redact(summary)

        # 4. Build prompt and call LLM
        prompt = build_brain_prompt(summary, custom_prompt)
        raw_response = await backend.analyze(
            prompt=prompt,
            max_tokens=2048,
            json_mode=True,
        )

        # 5. Parse JSON from markdown if wrapped
        json_text = _extract_json(raw_response)
        parsed = json.loads(json_text)

        # 6. Validate with Pydantic
        if isinstance(parsed, dict):
            # LLM may wrap array in an object; try to find the array
            for key in ("entries", "items", "results", "data"):
                if key in parsed:
                    parsed = parsed[key]
                    break
        adapter = TypeAdapter(list[BrainEntryExtract])
        extracts = adapter.validate_python(parsed)

        # 7. Post-LLM redaction (defense in depth)
        for extract in extracts:
            extract.content = redact(extract.content)

        # 8. Reopen DB for upsert
        db = await _open_db()
        try:
            for extract in extracts:
                entry_id = _compute_entry_id(extract.category, extract.title)
                await _upsert_entry(db, entry_id, user_id, extract, session_id)

            # 9. Mark session done
            await db.execute(
                "UPDATE sessions SET brain_status = 'done' WHERE session_id = ?",
                (session_id,),
            )
            await db.commit()
            logger.info(f"[brain] Synthesis complete for session {session_id}: {len(extracts)} entries")
        finally:
            await db.close()

    except (json.JSONDecodeError, ValidationError) as e:
        logger.warning(f"[brain] Invalid JSON/validation for session {session_id}: {e}")
        await _mark_failed(session_id)
    except Exception as e:
        logger.exception(f"[brain] Synthesis failed for session {session_id}: {e}")
        await _mark_failed(session_id)


def _extract_json(text: str) -> str:
    """Extract JSON from markdown code blocks or raw text."""
    text = text.strip()
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        return text[start:end].strip()
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 3:
            return parts[-2].strip()
    return text


async def _upsert_entry(db, entry_id: str, user_id: str, extract: BrainEntryExtract, session_id: str) -> None:
    """Upsert a single brain entry, reinforcing if already exists."""
    # Check for existing entry
    cursor = await db.execute(
        "SELECT confidence, hit_count, source_sessions FROM brain_entries WHERE id = ?",
        (entry_id,),
    )
    row = await cursor.fetchone()

    if row:
        # Reinforce existing entry
        existing_conf = row["confidence"] or 0.5
        new_conf = min(0.95, existing_conf + (1 - existing_conf) * 0.15)
        new_hit = (row["hit_count"] or 1) + 1

        # Append session_id to source_sessions (deduplicated)
        sessions: list[str] = json.loads(row["source_sessions"] or "[]")
        if session_id not in sessions:
            sessions.append(session_id)

        await db.execute(
            """
            UPDATE brain_entries SET
                confidence = ?,
                hit_count = ?,
                source_sessions = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (new_conf, new_hit, json.dumps(sessions), entry_id),
        )
        logger.info(f"[brain] Reinforced entry {entry_id}: hit_count={new_hit}")
    else:
        # New entry
        await db.execute(
            """
            INSERT INTO brain_entries (id, user_id, category, title, content, confidence, source_sessions, hit_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                user_id,
                extract.category,
                extract.title,
                extract.content,
                extract.confidence,
                json.dumps([session_id]),
                1,
            ),
        )


async def _mark_failed(session_id: str) -> None:
    """Mark a session's brain synthesis as failed."""
    try:
        db = await _open_db()
        await db.execute(
            "UPDATE sessions SET brain_status = 'failed' WHERE session_id = ?",
            (session_id,),
        )
        await db.commit()
        await db.close()
    except Exception as e:
        logger.error(f"[brain] Failed to mark session {session_id} as failed: {e}")


async def start_worker() -> None:
    """Start the brain synthesis background worker."""
    global _worker
    if _worker is None:
        _worker = PollingWorker(
            name="brain",
            config_loader=_load_config,
            fetch_pending=_fetch_pending_sessions,
            process_item=_process_session,
            open_db=_open_db,
            poll_interval=_POLL_INTERVAL,
        )
    await _worker.start()
    logger.info("[brain] Synthesizer worker started")


async def stop_worker() -> None:
    """Stop the brain synthesis background worker."""
    global _worker
    if _worker:
        await _worker.stop()
    logger.info("[brain] Synthesizer worker stopped")
