"""RCAWorker — asyncio background task that enriches issues with LLM RCA."""

import asyncio
import json
import os
from tracea.server.rca.backends import load_backend, RCABackend
from tracea.server.rca.models import RCABackendConfig, RCAContext
from tracea.server.rca.prompts import build_rca_prompt, load_custom_prompt

_POLLO_INTERVAL = 5  # seconds between pending-issue polls

_worker_task: asyncio.Task | None = None
_stop_event: asyncio.Event | None = None


def _load_config() -> RCABackendConfig:
    """Load RCA config from environment variables."""
    backend = os.getenv("TRACEA_RCA_BACKEND", "disabled")
    return RCABackendConfig(
        backend=backend,
        model=os.getenv("TRACEA_RCA_MODEL"),
        base_url=os.getenv("TRACEA_RCA_BASE_URL"),
        prompt_path=os.getenv("TRACEA_RCA_PROMPT_PATH"),
        redact_content=os.getenv("TRACEA_RCA_REDACT_CONTENT", "true").lower() == "true",
    )


async def _rca_worker_loop() -> None:
    """Poll for pending issues, run RCA, update status to done or failed."""
    global _stop_event
    config = _load_config()
    backend: RCABackend = load_backend(config)

    custom_prompt = load_custom_prompt(config.prompt_path)

    if config.backend != "disabled":
        print(f"[tracea] RCAWorker started with backend={config.backend}")

    from tracea.server.db import get_db

    while True:
        if _stop_event and _stop_event.is_set():
            break
        await asyncio.sleep(_POLLO_INTERVAL)

        if config.backend == "disabled":
            continue  # Nothing to do

        try:
            db_gen = get_db()
            db = await db_gen.__anext__()

            # Fetch pending issues
            cursor = await db.execute(
                "SELECT * FROM issues WHERE rca_status = 'pending' ORDER BY detected_at ASC LIMIT 10"
            )
            rows = await cursor.fetchall()

            for row in rows:
                issue_id = row["issue_id"]
                try:
                    # Parse captured_values JSON
                    captured = json.loads(row["captured_values"] or "{}")

                    # Get triggering event data
                    event_cursor = await db.execute(
                        "SELECT type, error, cost_usd, duration_ms, tool_name FROM events WHERE event_id = ?",
                        (row["event_id"],),
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
                        }]

                    session_aggregates = {
                        "cost_usd": row["session_cost_total"] or 0,
                        "duration_ms": row["session_duration_ms"] or 0,
                        "event_count": row["session_event_count"] or 0,
                    }

                    session_metadata = {}
                    if row["session_metadata"]:
                        try:
                            session_metadata = json.loads(row["session_metadata"])
                        except Exception:
                            pass

                    ctx = RCAContext(
                        rule_id=row["rule_id"] or "",
                        rule_description=row["rule_description"] or "",
                        issue_category=row["issue_type"],
                        severity=row["severity"],
                        triggering_events=triggering_events,
                        session_aggregates=session_aggregates,
                        session_metadata=session_metadata,
                    )

                    # Call LLM
                    prompt = build_rca_prompt(ctx, custom_prompt)
                    rca_text = await backend.analyze(ctx, prompt=prompt)

                    # Update issue
                    await db.execute(
                        "UPDATE issues SET rca_status = 'done', rca_text = ? WHERE issue_id = ?",
                        (rca_text, issue_id),
                    )
                    await db.commit()
                    print(f"[tracea] RCA completed for issue {issue_id}")

                except Exception as e:
                    print(f"[tracea] RCA failed for issue {issue_id}: {e}")
                    await db.execute(
                        "UPDATE issues SET rca_status = 'failed' WHERE issue_id = ?",
                        (issue_id,),
                    )
                    await db.commit()

        except Exception as e:
            print(f"[tracea] RCAWorker poll error: {e}")


async def start_worker() -> None:
    """Start the RCA background worker."""
    global _worker_task, _stop_event
    _stop_event = asyncio.Event()
    _worker_task = asyncio.create_task(_rca_worker_loop())


async def stop_worker() -> None:
    """Stop the RCA background worker."""
    global _stop_event, _worker_task
    if _stop_event:
        _stop_event.set()
    if _worker_task:
        _worker_task.cancel()
