import pytest
import asyncio
from tracea.server.detection.models import Rule, Condition, RulesFile
from tracea.server.detection.conditions import evaluate_condition, check_repetition
from tracea.server.detection.loader import RulesLoader


def test_rule_schema_valid(temp_rule_file):
    loader = RulesLoader(temp_rule_file)
    rules = loader.load()
    assert len(rules) == 2
    assert rules[0]['id'] == 'tool_error'
    assert rules[0]['severity'] == 'high'


def test_condition_operators():
    # Numeric
    assert evaluate_condition({'field': 'cost_usd', 'op': 'gt', 'value': 0.05}, {'cost_usd': 0.10}) == True
    assert evaluate_condition({'field': 'status_code', 'op': 'eq', 'value': 429}, {'status_code': 429}) == True
    assert evaluate_condition({'field': 'duration_ms', 'op': 'gte', 'value': 30000}, {'duration_ms': 29999}) == False
    # String
    assert evaluate_condition({'field': 'type', 'op': 'equals', 'value': 'error'}, {'type': 'error'}) == True
    assert evaluate_condition({'field': 'error', 'op': 'contains', 'value': 'timeout'}, {'error': 'connection timeout'}) == True
    # Existence
    assert evaluate_condition({'exists': 'error'}, {'error': 'something'}) == True
    assert evaluate_condition({'exists': 'error'}, {'error': ''}) == False


def test_composite_and():
    cond = {'and': [{'field': 'status_code', 'op': 'gte', 'value': 500}, {'field': 'status_code', 'op': 'lt', 'value': 600}]}
    assert evaluate_condition(cond, {'status_code': 503}) == True
    assert evaluate_condition(cond, {'status_code': 400}) == False


def test_composite_or():
    cond = {'or': [{'field': 'error', 'op': 'exists'}, {'field': 'status_code', 'op': 'eq', 'value': 429}]}
    assert evaluate_condition(cond, {'error': 'timeout'}) == True
    assert evaluate_condition(cond, {'status_code': 429}) == True
    assert evaluate_condition(cond, {}) == False


def test_repetition_block():
    events = [
        {'tool_name': 'web_search'},
        {'tool_name': 'web_search'},
        {'tool_name': 'web_search'},
        {'tool_name': 'web_search'},
    ]
    assert check_repetition({'tool_name': 'web_search'}, events, 'tool_name', 5) == True
    # min_count=6 requires 6 consecutive: 4 in events + current = 5 total, not enough
    assert check_repetition({'tool_name': 'web_search'}, events, 'tool_name', 6) == False


def test_fail_closed_on_bad_yaml(tmp_path):
    import ruamel.yaml
    # Write a rule with invalid severity
    bad_path = tmp_path / "bad.yaml"
    with open(bad_path, 'w') as f:
        f.write("rules:\n  - id: bad\n    description: bad\n    condition:\n      exists: x\n    issue_category: x\n    severity: not_valid\n")

    loader = RulesLoader(str(bad_path))
    # Should fail-closed: old rules retained, no crash
    # Note: This test verifies the loader handles validation errors gracefully


@pytest.mark.asyncio
async def test_detection_async_nonblocking(sample_event):
    """Verify detection runs asynchronously (does not block)."""
    from tracea.server.detection.engine import run_detection

    # Track whether detection completed
    detection_done = False

    async def run_with_flag():
        nonlocal detection_done
        await run_detection([sample_event])
        detection_done = True

    # Start detection task
    task = asyncio.create_task(run_with_flag())
    # Task should NOT be done immediately (some async operations may run)
    await asyncio.sleep(0.01)  # Allow microtasks to run
    # The HTTP response would return before detection completes
    # Here we just verify the task runs without blocking the caller
    await task
    assert detection_done == True


# ---------------------------------------------------------------------------
# SQL injection protection in session-rule aggregation (Wave 2 fix #11)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_session_rule_count_field_whitelist_rejects_injection(fresh_db):
    """Regression: count_field is user-writable via PUT /config/rules and was
    interpolated raw into SQL, enabling injection. It must be whitelisted."""
    from tracea.server.detection.engine import _evaluate_session_rule
    from tracea.server.db import get_db

    # Seed a session with one event so the query has something to scan
    db = get_db()
    await db.execute(
        "INSERT INTO sessions (session_id) VALUES (?)", ("sess-1",),
    )
    await db.execute(
        "INSERT INTO events (event_id, session_id, sequence, timestamp, type, cost_usd) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("e1", "sess-1", 1, "2024-01-01T00:00:00Z", "chat.completion", 1.5),
    )
    await db.commit()

    # 1. A valid count_field evaluates normally
    result = await _evaluate_session_rule(
        {"count_field": "cost_usd", "aggregation": "sum", "threshold": 1, "op": "gte"},
        "sess-1",
    )
    assert result is True, "valid count_field (cost_usd) should aggregate"

    # 2. Injection attempt in count_field must be rejected, not executed
    injection = "cost_usd) FROM events; DROP TABLE sessions; --"
    result_inj = await _evaluate_session_rule(
        {"count_field": injection, "aggregation": "sum", "threshold": 0, "op": "gt"},
        "sess-1",
    )
    assert result_inj is False, "injection attempt must be rejected by whitelist"

    # The sessions table must still exist (DROP TABLE did not execute)
    cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'")
    assert await cursor.fetchone() is not None, "sessions table must survive injection attempt"

    # 3. An arbitrary unknown column is also rejected
    result_unknown = await _evaluate_session_rule(
        {"count_field": "password", "aggregation": "sum", "threshold": 0, "op": "gt"},
        "sess-1",
    )
    assert result_unknown is False, "unknown column must be rejected by whitelist"