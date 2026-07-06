"""AlertDispatcher — resolves routing, manages rate limits, file watching, and webhook dispatch."""

import asyncio
import os
import time
from typing import Optional, Literal
from uuid import uuid4
import httpx
from watchfiles import awatch

from tracea.server.alerts.models import (
    AlertRoute,
    AlertsConfig,
    load_alerts_config,
    format_alert_payload,
    exponential_backoff_with_jitter,
)
from tracea.server.db import get_db

# Watcher config globals
_alerts_config: AlertsConfig | None = None
_config_lock = asyncio.Lock()
_stop_watching: asyncio.Event | None = None
_alerts_watcher_task: asyncio.Task | None = None

# Router config globals
_DEDUP_WINDOW = 60  # seconds
_dedup_cache: dict[tuple[str, str], float] = {}  # (session_id, issue_category) -> last_sent_ts
_dedup_lock = asyncio.Lock()

_token_buckets: dict[str, tuple[int, float]] = {}
_bucket_lock = asyncio.Lock()
_RATE_LIMIT_RPM = 60  # messages per minute

# Dispatcher globals
_DISPATCH_QUEUE: asyncio.Queue = asyncio.Queue()
_worker_task: asyncio.Task | None = None
_stop_event: asyncio.Event | None = None
_RETRY_ATTEMPTS = 3
_BASE_URL = os.getenv("TRACEA_BASE_URL", "http://localhost:8080")


# --- 1. AlertWatcher logic (Hot-reloads alerts.yaml) ---

async def reload_alerts(path: str | None = None) -> None:
    """Reload alerts config atomically."""
    global _alerts_config
    alert_path = path or os.getenv("TRACEA_ALERTS_PATH", "./data/alerts.yaml")
    try:
        config = load_alerts_config(alert_path)
        async with _config_lock:
            _alerts_config = config
        print(f"[tracea] Reloaded alerts config from {alert_path}")
    except Exception as e:
        print(f"[tracea] Alerts reload failed: {e}. Retaining last valid config.")


async def get_alerts_config() -> AlertsConfig | None:
    async with _config_lock:
        return _alerts_config


async def _watch_loop(path: str | None = None) -> None:
    global _stop_watching
    alert_path = path or os.getenv("TRACEA_ALERTS_PATH", "./data/alerts.yaml")
    backoff = 1.0
    while True:
        if _stop_watching and _stop_watching.is_set():
            return
        try:
            await reload_alerts(alert_path)
            async for changes in awatch(alert_path):
                await reload_alerts(alert_path)
                if _stop_watching and _stop_watching.is_set():
                    return
            backoff = 1.0
        except asyncio.CancelledError:
            return
        except Exception as e:
            print(f"[tracea] AlertWatcher error: {e}. Reconnecting in {int(backoff)}s...")
            try:
                await asyncio.wait_for(_stop_watching.wait(), timeout=backoff)  # type: ignore[arg-type]
                return
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, 30.0)


async def start_watching(path: str | None = None) -> None:
    global _stop_watching, _alerts_watcher_task
    _stop_watching = asyncio.Event()
    _alerts_watcher_task = asyncio.create_task(_watch_loop(path))


async def stop_watching() -> None:
    global _stop_watching, _alerts_watcher_task
    if _stop_watching:
        _stop_watching.set()
    if _alerts_watcher_task:
        _alerts_watcher_task.cancel()


# --- 2. AlertRouter logic (Resolves routes, dedup, and rate limits) ---

async def _resolve_route(issue_category: str) -> Optional[AlertRoute]:
    """Find the most specific matching route for an issue category."""
    config = await get_alerts_config()
    if not config:
        return None

    # Exact match first
    for route in config.routes:
        if route.issue_category == issue_category:
            return route

    # Default wildcard match
    for route in config.routes:
        if route.issue_category == "*":
            return route

    return None


def _is_duplicate(session_id: str, issue_category: str) -> bool:
    """Check if this (session_id, issue_category) combo was already alerted within dedup window."""
    key = (session_id, issue_category)
    now = time.time()

    if key in _dedup_cache:
        last_sent = _dedup_cache[key]
        if now - last_sent < _DEDUP_WINDOW:
            return True

    return False


def _mark_alerted(session_id: str, issue_category: str) -> None:
    """Record that an alert was sent for this combo."""
    key = (session_id, issue_category)
    _dedup_cache[key] = time.time()


async def _check_rate_limit_async(bucket_key: str, now: float, refill_rate: float, max_tokens: int) -> bool:
    global _token_buckets
    async with _bucket_lock:
        if bucket_key not in _token_buckets:
            _token_buckets[bucket_key] = (max_tokens, now)
            return True

        tokens, last_refill = _token_buckets[bucket_key]
        elapsed = now - last_refill
        tokens = min(max_tokens, tokens + elapsed * refill_rate)

        if tokens >= 1:
            _token_buckets[bucket_key] = (tokens - 1, now)
            return True
        else:
            _token_buckets[bucket_key] = (tokens, now)
            return False


async def get_route_for_issue(session_id: str, issue_category: str) -> Optional[AlertRoute]:
    """Resolve route + check dedup + check rate limit. Returns route if should fire.

    NOTE: This does NOT mark the combo as alerted — that happens only after a
    successful send (or permanent failure → dead-letter) in ``_dispatch_loop``.
    Marking here would cause silently-dropped alerts when the webhook fails
    permanently, because the dedup window would suppress the next attempt.
    """
    route = await _resolve_route(issue_category)
    if not route:
        return None

    if _is_duplicate(session_id, issue_category):
        return None

    route_rpm = route.rate_limit_rpm if route.rate_limit_rpm is not None else _RATE_LIMIT_RPM
    allowed = await _check_rate_limit_async(route.webhook_url, time.time(), route_rpm / 60.0, route_rpm)
    if not allowed:
        return None

    return route


# --- 3. AlertDispatcher logic (Queue, webhook execution with retries) ---

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
    db = get_db()
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
            db = get_db()
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

        if success:
            # Only record dedup after a confirmed successful delivery.
            _mark_alerted(session_id, issue_category)
        else:
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