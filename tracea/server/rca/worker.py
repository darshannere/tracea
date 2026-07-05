"""RCAWorker — asyncio background task that enriches issues with LLM RCA."""

import asyncio
import json
import os

import aiosqlite

from tracea.server.rca.backends import load_backend, RCABackend
from tracea.server.rca.models import RCABackendConfig, RCAContext
from tracea.server.rca.prompts import build_rca_prompt, load_custom_prompt
from tracea.server.settings import get_rca_config

from tracea.server.worker_base import PollingWorker

_POLL_INTERVAL = 5  # seconds between pending-issue polls
_worker: PollingWorker | None = None


async def _load_config() -> RCABackendConfig:
    """Load RCA config from DB settings, falling back to env vars."""
    cfg = await get_rca_config()
    return RCABackendConfig(
        backend=cfg["backend"],
        model=cfg.get("model") or None,
        base_url=cfg.get("base_url") or None,
        prompt_path=cfg.get("prompt_path") or None,
        redact_content=cfg.get("redact_content", True),
        max_tokens=cfg.get("max_tokens", 2048),
        api_key=cfg.get("api_key") or None,
    )


async def _fetch_event_timeline(db, session_id: str, trigger_event_id: str, limit: int = 40) -> list[dict]:
    """Fetch chronological events around the trigger for context."""
    cursor = await db.execute(
        """
        SELECT event_id, type, tool_name, model, error, cost_usd, duration_ms,
               input_tokens, output_tokens, sequence, timestamp
        FROM events
        WHERE session_id = ?
        ORDER BY sequence ASC
        LIMIT ?
        """,
        (session_id, limit),
    )
    rows = await cursor.fetchall()
    timeline = []
    for row in rows:
        timeline.append({
            "event_id": row["event_id"],
            "sequence": row["sequence"],
            "type": row["type"] or "",
            "tool_name": row["tool_name"] or "",
            "model": row["model"] or "",
            "error": row["error"] or "",
            "cost_usd": row["cost_usd"] or 0,
            "duration_ms": row["duration_ms"] or 0,
            "input_tokens": row["input_tokens"] or 0,
            "output_tokens": row["output_tokens"] or 0,
            "timestamp": row["timestamp"] or "",
            "is_trigger": row["event_id"] == trigger_event_id,
        })
    return timeline


async def _fetch_tool_breakdown(db, session_id: str) -> list[dict]:
    """Fetch tool usage stats for the session."""
    cursor = await db.execute(
        """
        SELECT tool_name,
               COUNT(*) as call_count,
               SUM(CASE WHEN error IS NOT NULL AND error != '' THEN 1 ELSE 0 END) as error_count,
               AVG(duration_ms) as avg_duration_ms,
               SUM(cost_usd) as total_cost_usd
        FROM events
        WHERE session_id = ? AND tool_name IS NOT NULL AND tool_name != ''
        GROUP BY tool_name
        ORDER BY call_count DESC
        """,
        (session_id,),
    )
    rows = await cursor.fetchall()
    return [
        {
            "tool_name": row["tool_name"],
            "call_count": row["call_count"],
            "error_count": row["error_count"],
            "avg_duration_ms": round(row["avg_duration_ms"] or 0, 2),
            "total_cost_usd": round(row["total_cost_usd"] or 0, 6),
        }
        for row in rows
    ]


async def _fetch_model_breakdown(db, session_id: str) -> list[dict]:
    """Fetch LLM model usage stats for the session."""
    cursor = await db.execute(
        """
        SELECT model,
               COUNT(*) as call_count,
               SUM(input_tokens) as total_input_tokens,
               SUM(output_tokens) as total_output_tokens,
               SUM(cost_usd) as total_cost_usd
        FROM events
        WHERE session_id = ? AND model IS NOT NULL AND model != ''
        GROUP BY model
        ORDER BY call_count DESC
        """,
        (session_id,),
    )
    rows = await cursor.fetchall()
    return [
        {
            "model": row["model"],
            "call_count": row["call_count"],
            "total_input_tokens": row["total_input_tokens"] or 0,
            "total_output_tokens": row["total_output_tokens"] or 0,
            "total_cost_usd": round(row["total_cost_usd"] or 0, 6),
        }
        for row in rows
    ]


async def _fetch_latency_stats(db, session_id: str) -> dict:
    """Fetch latency statistics for the session."""
    cursor = await db.execute(
        """
        SELECT MIN(duration_ms) as min_ms,
               MAX(duration_ms) as max_ms,
               AVG(duration_ms) as avg_ms
        FROM events
        WHERE session_id = ? AND duration_ms IS NOT NULL
        """,
        (session_id,),
    )
    row = await cursor.fetchone()
    stats = {
        "min_ms": row["min_ms"] or 0,
        "max_ms": row["max_ms"] or 0,
        "avg_ms": round(row["avg_ms"] or 0, 2),
    }
    # Approximate p95 using ordered subquery (SQLite has no native percentile)
    cursor = await db.execute(
        """
        SELECT duration_ms FROM events
        WHERE session_id = ? AND duration_ms IS NOT NULL
        ORDER BY duration_ms ASC
        """,
        (session_id,),
    )
    durations = [r["duration_ms"] for r in await cursor.fetchall()]
    if durations:
        p95_idx = int(len(durations) * 0.95)
        stats["p95_ms"] = durations[min(p95_idx, len(durations) - 1)]
    else:
        stats["p95_ms"] = 0
    return stats


async def _fetch_related_issues(db, session_id: str, exclude_issue_id: str) -> list[dict]:
    """Fetch other issues in the same session."""
    cursor = await db.execute(
        """
        SELECT issue_id, issue_type, severity, detected_at, rca_status
        FROM issues
        WHERE session_id = ? AND issue_id != ?
        ORDER BY detected_at ASC
        """,
        (session_id, exclude_issue_id),
    )
    rows = await cursor.fetchall()
    return [
        {
            "issue_id": row["issue_id"],
            "issue_type": row["issue_type"],
            "severity": row["severity"],
            "detected_at": row["detected_at"],
            "rca_status": row["rca_status"],
        }
        for row in rows
    ]


async def _fetch_historical_frequency(db, rule_id: str) -> dict:
    """Count how often this rule fired in the last 24 hours."""
    cursor = await db.execute(
        """
        SELECT COUNT(*) as count_24h,
               COUNT(DISTINCT session_id) as affected_sessions
        FROM issues
        WHERE rule_id = ? AND detected_at >= datetime('now', '-1 day')
        """,
        (rule_id,),
    )
    row = await cursor.fetchone()
    return {
        "count_24h": row["count_24h"] or 0,
        "affected_sessions": row["affected_sessions"] or 0,
    }


async def _fetch_session_start(db, session_id: str) -> str | None:
    """Fetch session start time."""
    cursor = await db.execute(
        "SELECT started_at FROM sessions WHERE session_id = ?",
        (session_id,),
    )
    row = await cursor.fetchone()
    return row["started_at"] if row else None


async def _open_db() -> aiosqlite.Connection:
    """Open a fresh SQLite connection (not the singleton)."""
    from tracea.server.db import DB_PATH

    db = await aiosqlite.connect(DB_PATH, isolation_level=None)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    return db


async def _process_issue(backend: RCABackend, config: RCABackendConfig, custom_prompt: str | None, row: aiosqlite.Row) -> None:
    """Process a single issue: fetch context, call LLM, update DB.

    Manages its own DB connection lifecycle: opens, fetches context, closes
    before the LLM call, reopens for update, then closes.
    """
    issue_id = row["issue_id"]
    try:
        session_id = row["session_id"]
        event_id = row["event_id"]
        rule_id = row["rule_id"] or ""

        # 1. Open DB and fetch all context
        db = await _open_db()
        try:
            # Parse captured_values JSON
            captured = json.loads(row["captured_values"] or "{}")

            # Get triggering event data
            event_cursor = await db.execute(
                "SELECT type, error, cost_usd, duration_ms, tool_name, model, sequence "
                "FROM events WHERE event_id = ?",
                (event_id,),
            )
            event_row = await event_cursor.fetchone()
            triggering_events = []
            if event_row:
                triggering_events = [{
                    "type": event_row["type"] or "",
                    "error": event_row["error"] or "",
                    "cost_usd": event_row["cost_usd"] or 0,
                    "duration_ms": event_row["duration_ms"] or 0,
                    "tool_name": event_row["tool_name"] or "",
                    "model": event_row["model"] or "",
                    "sequence": event_row["sequence"] or 0,
                }]

            session_aggregates = {
                "cost_usd": row["session_cost_total"] or 0,
                "duration_ms": row["session_duration_ms"] or 0,
                "event_count": row["session_event_count"] or 0,
            }

            # Add token aggregates if available
            token_cursor = await db.execute(
                "SELECT SUM(input_tokens) as input_tokens, SUM(output_tokens) as output_tokens "
                "FROM events WHERE session_id = ?",
                (session_id,),
            )
            token_row = await token_cursor.fetchone()
            if token_row:
                session_aggregates["input_tokens"] = token_row["input_tokens"] or 0
                session_aggregates["output_tokens"] = token_row["output_tokens"] or 0

            session_metadata = {}
            if row["session_metadata"]:
                try:
                    session_metadata = json.loads(row["session_metadata"])
                except Exception:
                    pass

            # Gather verbose context
            event_timeline = await _fetch_event_timeline(db, session_id, event_id)
            tool_breakdown = await _fetch_tool_breakdown(db, session_id)
            model_breakdown = await _fetch_model_breakdown(db, session_id)
            latency_stats = await _fetch_latency_stats(db, session_id)
            related_issues = await _fetch_related_issues(db, session_id, issue_id)
            historical_frequency = await _fetch_historical_frequency(db, rule_id)
            session_start_time = await _fetch_session_start(db, session_id)

            rule_config_snapshot = {}
            if row["rule_config_snapshot"]:
                try:
                    rule_config_snapshot = json.loads(row["rule_config_snapshot"])
                except Exception:
                    pass
        finally:
            await db.close()

        ctx = RCAContext(
            rule_id=rule_id,
            rule_description=row["rule_description"] or "",
            issue_category=row["issue_type"],
            severity=row["severity"],
            triggering_events=triggering_events,
            session_aggregates=session_aggregates,
            session_metadata=session_metadata,
            session_start_time=session_start_time,
            event_timeline=event_timeline,
            tool_breakdown=tool_breakdown,
            model_breakdown=model_breakdown,
            latency_stats=latency_stats,
            related_issues=related_issues,
            historical_frequency=historical_frequency,
            rule_config_snapshot=rule_config_snapshot,
        )

        # 2. Call LLM (DB is closed)
        prompt = build_rca_prompt(ctx, custom_prompt, redact_content=config.redact_content)
        rca_text = await backend.analyze(prompt=prompt, max_tokens=config.max_tokens)

        # 3. Try to parse structured output
        rca_structured = None
        try:
            if "```json" in rca_text:
                json_start = rca_text.index("```json") + 7
                json_end = rca_text.index("```", json_start)
                rca_structured = rca_text[json_start:json_end].strip()
            elif "```" in rca_text:
                parts = rca_text.split("```")
                if len(parts) >= 3:
                    rca_structured = parts[-2].strip()
        except Exception:
            pass

        # 4. Reopen DB to update issue
        db = await _open_db()
        try:
            await db.execute(
                "UPDATE issues SET rca_status = 'done', rca_text = ?, rca_structured = ? WHERE issue_id = ?",
                (rca_text, rca_structured, issue_id),
            )
            await db.commit()
            print(f"[tracea] RCA completed for issue {issue_id}")
        finally:
            await db.close()

    except Exception as e:
        print(f"[tracea] RCA failed for issue {issue_id}: {e}")
        db = await _open_db()
        try:
            await db.execute(
                "UPDATE issues SET rca_status = 'failed' WHERE issue_id = ?",
                (issue_id,),
            )
            await db.commit()
        finally:
            await db.close()


async def _fetch_pending_issues(db) -> list[aiosqlite.Row]:
    """Fetch pending issues."""
    cursor = await db.execute(
        "SELECT * FROM issues WHERE rca_status = 'pending' ORDER BY detected_at ASC LIMIT 5"
    )
    return await cursor.fetchall()


async def start_worker() -> None:
    """Start the RCA background worker."""
    global _worker
    if _worker is None:
        _worker = PollingWorker(
            name="rca",
            config_loader=_load_config,
            fetch_pending=_fetch_pending_issues,
            process_item=_process_issue,
            open_db=_open_db,
            poll_interval=_POLL_INTERVAL,
        )
    await _worker.start()


async def stop_worker() -> None:
    """Stop the RCA background worker."""
    global _worker
    if _worker:
        await _worker.stop()

