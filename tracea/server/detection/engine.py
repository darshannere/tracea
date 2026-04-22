"""DetectionEngine — evaluates rules against ingested events asynchronously."""
import asyncio
import json
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
from tracea.server.detection.watcher import get_rules
from tracea.server.detection.conditions import evaluate_condition, check_repetition

# In-memory deduplication: track processed event IDs per boot
_processed_event_ids: set[str] = set()

# Session sliding windows for repetition detection
_recent_by_session: dict[str, list[dict]] = {}


def _event_to_dict(event) -> dict:
    """Convert TracedEvent or dict to a flat dict for condition evaluation."""
    if isinstance(event, dict):
        return event
    # TracedEvent — extract fields
    return {
        'event_id': str(getattr(event, 'event_id', '')),
        'session_id': str(getattr(event, 'session_id', '')),
        'type': getattr(event, 'type', ''),
        'provider': getattr(event, 'provider', ''),
        'model': getattr(event, 'model', ''),
        'duration_ms': getattr(event, 'duration_ms', 0) or 0,
        'cost_usd': getattr(event, 'cost_usd', None),
        'status_code': getattr(event, 'status_code', None),
        'error': getattr(event, 'error', '') or '',
        'content': getattr(event, 'content', '') or '',
        'tool_name': getattr(event, 'tool_name', '') or '',
    }


def _rule_matches(rule: dict, event_dict: dict) -> bool:
    """Check if a rule matches an event."""
    condition = rule.get('condition', {})
    if not evaluate_condition(condition, event_dict):
        return False

    # Check repetition block
    rep = rule.get('repetition')
    if rep:
        rep_field = rep.get('field', '')
        min_count = rep.get('min_count', 2)
        if not _check_repetition_for_rule(event_dict, rep_field, min_count, rule.get('id', '')):
            return False

    # Check session_rules (count-within-session aggregation)
    sess = rule.get('session_rules')
    if sess:
        if not _evaluate_session_rule_sync(sess, event_dict.get('session_id', '')):
            return False

    return True


def _check_repetition_for_rule(event_dict: dict, rep_field: str, min_count: int, rule_id: str) -> bool:
    """Check repetition using session sliding window."""
    session_id = event_dict.get('session_id', '')
    if session_id not in _recent_by_session:
        _recent_by_session[session_id] = []

    recent = _recent_by_session[session_id]
    current_value = event_dict.get(rep_field)

    if current_value is None:
        return True  # No field to check repetition against

    # Count consecutive occurrences
    count = 1
    for prev in reversed(recent):
        if prev.get(rep_field) == current_value:
            count += 1
        else:
            break

    # Add current event to window (keep last 20 per session)
    _recent_by_session[session_id] = (recent + [event_dict])[-20:]

    return count >= min_count


def _evaluate_session_rule_sync(sess: dict, session_id: str) -> bool:
    """Evaluate a session_rules aggregation synchronously."""
    count_field = sess.get('count_field', '')
    aggregation = sess.get('aggregation', 'sum')
    threshold = sess.get('threshold', 0)
    op = sess.get('op', 'gt')

    if not session_id:
        return False

    from tracea.server.db import get_db
    import asyncio

    # Get the event loop - this is called from async context
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        db_gen = get_db()
        db = loop.run_until_complete(db_gen.__anext__())
    else:
        # We need to run sync, but we're in async context
        # For now, return True (skip session rule check if DB unavailable)
        return True

    # Build query for aggregation
    col_map = {
        'sum': f'SUM({count_field})',
        'count': 'COUNT(*)',
        'max': f'MAX({count_field})',
        'avg': f'AVG({count_field})',
    }
    col = col_map.get(aggregation, count_field)

    try:
        cursor = loop.run_until_complete(db.execute(f"SELECT {col} as val FROM events WHERE session_id = ?", (session_id,)))
        row = loop.run_until_complete(cursor.fetchone())
        if row is None:
            return False
        val = row['val'] or 0
        OPERATORS = {
            'gt': val > threshold,
            'gte': val >= threshold,
            'lt': val < threshold,
            'lte': val <= threshold,
            'eq': val == threshold,
        }
        return OPERATORS.get(op, False)
    except Exception:
        return False


async def run_detection(events: list) -> None:
    """Evaluate rules against a batch of events.

    Called via asyncio.create_task after SQLite commit.
    Does NOT block the HTTP ingest response.
    """
    global _processed_event_ids
    rules = await get_rules()
    if not rules:
        return

    for event in events:
        if hasattr(event, 'get'):
            event_id = str(event.get('event_id', ''))
        else:
            event_id = str(getattr(event, 'event_id', ''))
        if event_id in _processed_event_ids:
            continue
        _processed_event_ids.add(event_id)

        event_dict = _event_to_dict(event)

        for rule in rules:
            try:
                if _rule_matches(rule, event_dict):
                    await _create_issue(event, rule, event_dict)
            except Exception as e:
                print(f"[tracea] Rule evaluation error for {rule.get('id', 'unknown')}: {e}")


async def _create_issue(event, rule: dict, event_dict: dict) -> None:
    """Write an issue to the SQLite database with full DET-08 metadata."""
    issue_id = str(uuid4())
    session_id = str(getattr(event, 'session_id', event_dict.get('session_id', '')))
    event_id = str(getattr(event, 'event_id', event_dict.get('event_id', '')))

    # Build captured_values snapshot (what triggered the rule)
    condition = rule.get('condition', {})
    if 'exists' in condition:
        field_name = condition['exists']
        field_value = event_dict.get(field_name, '')
        op_used = 'exists'
        threshold_used = None
    elif 'field' in condition:
        field_name = condition.get('field', '')
        field_value = event_dict.get(field_name, '')
        op_used = condition.get('op', '')
        threshold_used = condition.get('value')
    else:
        field_name = ''
        field_value = ''
        op_used = ''
        threshold_used = None

    captured_values = json.dumps({
        'field': field_name,
        'op': op_used,
        'value': field_value,
        'threshold': threshold_used,
        'triggered_event_id': event_id,
    })

    # Session aggregates (query at detection time for v0.1)
    session_cost = 0.0
    session_duration = 0
    session_event_count = 0
    try:
        from tracea.server.db import get_db
        db_gen = get_db()
        db = await db_gen.__anext__()

        cursor = await db.execute(
            "SELECT SUM(cost_usd) as total_cost, SUM(duration_ms) as total_duration, COUNT(*) as event_count FROM events WHERE session_id = ?",
            (session_id,)
        )
        row = await cursor.fetchone()
        if row:
            session_cost = row['total_cost'] or 0.0
            session_duration = row['total_duration'] or 0
            session_event_count = row['event_count'] or 0
    except Exception:
        pass

    # First/last event IDs
    first_event_id = event_id
    last_event_id = event_id

    # Error message
    error_msg = event_dict.get('error', '') or ''

    # Session metadata from tracea.session(metadata={...}) — stored in event.metadata
    session_meta = {}
    metadata_val = getattr(event, 'metadata', {}) or {}
    if isinstance(metadata_val, dict):
        session_meta = metadata_val.get('session_metadata', {})
    session_metadata_json = json.dumps(session_meta)

    # Rule config snapshot
    rule_config_snapshot = json.dumps(rule)

    try:
        from tracea.server.db import get_db
        db_gen = get_db()
        db = await db_gen.__anext__()
        await db.execute("""
            INSERT INTO issues (
                issue_id, session_id, event_id, rule_name, issue_type, severity,
                rca_status, rule_id, rule_description, captured_values,
                session_cost_total, session_duration_ms, session_event_count,
                first_event_id, last_event_id, error_message,
                session_metadata, rule_config_snapshot
            ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            issue_id,
            session_id,
            event_id,
            rule.get('id', ''),
            rule.get('issue_category', ''),
            rule.get('severity', 'medium'),
            rule.get('id', ''),          # rule_id
            rule.get('description', ''),  # rule_description
            captured_values,
            session_cost,
            session_duration,
            session_event_count,
            first_event_id,
            last_event_id,
            error_msg,
            session_metadata_json,
            rule_config_snapshot,
        ))
        await db.execute(
            "UPDATE sessions SET issue_count = issue_count + 1 WHERE session_id = ?",
            (session_id,)
        )
        await db.commit()
        print(f"[tracea] Issue created: {rule.get('id', 'unknown')} ({rule.get('issue_category', '')}) for event {event_id}")

        # Fire alert (does NOT wait for RCA — fire-and-forget)
        asyncio.create_task(_enqueue_alert(
            issue_id=issue_id,
            session_id=session_id,
            issue_type=rule.get('issue_category', ''),
            severity=rule.get('severity', 'medium'),
            session_cost_total=session_cost,
            session_duration_ms=session_duration,
            session_event_count=session_event_count,
            error_message=error_msg,
            rule_id=rule.get('id', ''),
            rule_description=rule.get('description', ''),
            detected_at=None,  # filled by dispatcher from DB if needed
        ))
    except Exception as e:
        print(f"[tracea] Failed to create issue: {e}")


async def _enqueue_alert(
    issue_id: str,
    session_id: str,
    issue_type: str,
    severity: str,
    session_cost_total: float,
    session_duration_ms: int,
    session_event_count: int,
    error_message: str,
    rule_id: str,
    rule_description: str,
    detected_at: str | None,
) -> None:
    """Enqueue issue for AlertDispatcher. Import lazily to avoid circular."""
    from tracea.server.alerts.dispatcher import enqueue_issue
    issue = {
        "issue_id": issue_id,
        "session_id": session_id,
        "issue_type": issue_type,
        "severity": severity,
        "session_cost_total": session_cost_total,
        "session_duration_ms": session_duration_ms,
        "session_event_count": session_event_count,
        "error_message": error_message,
        "rule_id": rule_id,
        "rule_description": rule_description,
        "detected_at": detected_at or _now_iso(),
    }
    await enqueue_issue(issue)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()