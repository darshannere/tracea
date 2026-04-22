"""AlertDispatcher — fires webhooks on issue creation, with retry + dead-letter."""

import asyncio
import os
import httpx
from tracea.server.alerts.router import get_route_for_issue
from tracea.server.alerts.formatters import format_alert_payload
from tracea.server.alerts.backoff import exponential_backoff_with_jitter
from tracea.server.db import get_db

_DISPATCH_QUEUE: asyncio.Queue = asyncio.Queue()
_worker_task: asyncio.Task | None = None
_stop_event: asyncio.Event | None = None
_RETRY_ATTEMPTS = 3
_BASE_URL = os.getenv("TRACEA_BASE_URL", "http://localhost:8080")


async def enqueue_issue(issue: dict) -> None:
    """Called by detection engine or ingest route when an issue is created."""
    await _DISPATCH_QUEUE.put(issue)


async def _send_webhook(route_type: str, webhook_url: str, payload: dict) -> tuple[bool, str]:
    """Send webhook. Returns (success, error_message)."""
    url = webhook_url.replace("${TRACEA_BASE_URL}", _BASE_URL)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code < 400:
                return True, ""
            else:
                return False, f"HTTP {response.status_code}: {response.text[:200]}"
    except httpx.TimeoutException:
        return False, "Timeout after 10s"
    except Exception as e:
        return False, str(e)[:200]


async def _record_failure(issue_id: str, webhook_url: str, error: str, attempt: int) -> None:
    """Record permanent failure to webhook_failures dead-letter table."""
    from tracea.server.db import get_db
    from uuid import uuid4
    db_gen = get_db()
    db = await db_gen.__anext__()
    await db.execute("""
        INSERT INTO webhook_failures (id, issue_id, destination_url, status_code, response_body, attempt_count, created_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
    """, (str(uuid4()), issue_id, webhook_url, -1, error, attempt))
    await db.commit()


async def _dispatch_loop() -> None:
    """Main dispatch loop: consume queue, send webhooks, retry on failure."""
    global _stop_event
    while True:
        if _stop_event and _stop_event.is_set():
            break
        try:
            # Wait for an issue with timeout so we can check _stop_event
            issue = await asyncio.wait_for(_DISPATCH_QUEUE.get(), timeout=2.0)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            break

        session_id = issue.get("session_id", "")
        issue_category = issue.get("issue_type", "")
        issue_id = issue.get("issue_id", "")

        # Resolve route (dedup + rate limit)
        route = await get_route_for_issue(session_id, issue_category)
        if not route:
            continue

        # Enrich issue with session start time (and RCA if already done)
        try:
            db_gen = get_db()
            db = await db_gen.__anext__()
            cursor = await db.execute(
                "SELECT started_at FROM sessions WHERE session_id = ?",
                (session_id,)
            )
            row = await cursor.fetchone()
            session_start = row["started_at"] if row else None

            # Also fetch RCA text if already done
            rca_cursor = await db.execute(
                "SELECT rca_text, rca_structured FROM issues WHERE issue_id = ?",
                (issue_id,)
            )
            rca_row = await rca_cursor.fetchone()
            if rca_row and rca_row["rca_text"]:
                issue["rca_text"] = rca_row["rca_text"]
            if rca_row and rca_row["rca_structured"]:
                issue["rca_structured"] = rca_row["rca_structured"]
        except Exception:
            session_start = None

        # Build payload
        payload = format_alert_payload(issue, route.route_type, _BASE_URL, session_start)

        # Try with retry
        success = False
        last_error = ""
        for attempt in range(_RETRY_ATTEMPTS):
            ok, err = await _send_webhook(route.route_type, route.webhook_url, payload)
            if ok:
                success = True
                break
            last_error = err
            if attempt < _RETRY_ATTEMPTS - 1:
                delay = await exponential_backoff_with_jitter(attempt)
                await asyncio.sleep(delay)

        if not success:
            print(f"[tracea] Alert failed for issue {issue_id} after {_RETRY_ATTEMPTS} attempts: {last_error}")
            await _record_failure(issue_id, route.webhook_url, last_error, _RETRY_ATTEMPTS)


async def start_dispatcher() -> None:
    global _worker_task, _stop_event
    _stop_event = asyncio.Event()
    _worker_task = asyncio.create_task(_dispatch_loop())
    print("[tracea] AlertDispatcher started")


async def stop_dispatcher() -> None:
    global _stop_event, _worker_task
    if _stop_event:
        _stop_event.set()
    if _worker_task:
        _worker_task.cancel()
    print("[tracea] AlertDispatcher stopped")