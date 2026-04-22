"""AlertRouter — resolves issue -> route, handles deduplication + rate limiting."""

import asyncio
import os
import time
from typing import Optional
from tracea.server.alerts.models import AlertRoute, AlertsConfig, load_alerts_config
from tracea.server.alerts.watcher import get_alerts_config

_DEDUP_WINDOW = 60  # 60 seconds per ALT-05 requirement
_dedup_cache: dict[tuple[str, str], float] = {}  # (session_id, issue_category) -> last_sent_ts
_dedup_lock = asyncio.Lock()

# Token bucket: per destination URL -> (tokens, last_refill)
_token_buckets: dict[str, tuple[int, float]] = {}
_bucket_lock = asyncio.Lock()
_RATE_LIMIT_RPM = 60  # 1 msg/sec default


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
    """Resolve route + check dedup + check rate limit. Returns route if should fire."""
    route = await _resolve_route(issue_category)
    if not route:
        return None

    if _is_duplicate(session_id, issue_category):
        return None

    route_rpm = route.rate_limit_rpm if route.rate_limit_rpm is not None else _RATE_LIMIT_RPM
    allowed = await _check_rate_limit_async(route.webhook_url, time.time(), route_rpm / 60.0, route_rpm)
    if not allowed:
        return None

    _mark_alerted(session_id, issue_category)
    return route