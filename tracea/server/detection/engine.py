"""DetectionEngine — evaluates rules against ingested events asynchronously."""
import asyncio
from typing import Optional
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
        event_id = str(getattr(event, 'event_id', event.get('event_id', '')))
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
    """Write an issue to the SQLite database."""
    from tracea.server.db import get_db
    from uuid import uuid4

    issue_id = str(uuid4())
    session_id = str(getattr(event, 'session_id', event_dict.get('session_id', '')))
    event_id = str(getattr(event, 'event_id', event_dict.get('event_id', '')))

    try:
        db_gen = get_db()
        db = await db_gen.__anext__()
        await db.execute("""
            INSERT INTO issues (issue_id, session_id, event_id, rule_name, issue_type, severity, rca_status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
        """, (
            issue_id,
            session_id,
            event_id,
            rule.get('id', ''),
            rule.get('issue_category', ''),
            rule.get('severity', 'medium'),
        ))
        await db.commit()
        print(f"[tracea] Issue created: {rule.get('id', 'unknown')} for event {event_id}")
    except Exception as e:
        print(f"[tracea] Failed to create issue: {e}")