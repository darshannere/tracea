import asyncio
import os
import tempfile
import pytest
from tracea.server.db import init_db, close_db, get_db
import tracea.server.db as dbmod
import tracea.server.detection.watcher as watcher
from tracea.server.otel.mapper import persist_metrics

def set_rules(rules: list[dict]):
    watcher._rules = rules

@pytest.mark.asyncio
async def test_metric_rule_cost_spike_fires(fresh_db):
    set_rules([{
        'id': 'cost_spike',
        'description': 'cost > 0.01',
        'metric': {
            'name': 'claude_code.cost.usage',
            'aggregation': 'sum',
            'window': 'session',
            'op': 'gt',
            'threshold': 0.01
        },
        'issue_category': 'high_cost',
        'severity': 'high'
    }])

    # Persist a metric above the threshold
    await persist_metrics([{
        'name': 'claude_code.cost.usage',
        'value': 0.05,
        'attributes': {},
        'timestamp_unix_nano': 1700000000_000000000,
        'resource_attrs': {'session_id': 's1'}
    }])

    # Allow run_metric_detection background task to execute
    await asyncio.sleep(0.1)

    db = get_db()
    cur = await db.execute("SELECT rule_id, captured_values FROM issues WHERE rule_id = 'cost_spike'")
    rows = [dict(r) for r in await cur.fetchall()]
    assert len(rows) == 1
    assert rows[0]['rule_id'] == 'cost_spike'


@pytest.mark.asyncio
async def test_metric_rule_below_threshold_does_not_fire(fresh_db):
    set_rules([{
        'id': 'cost_spike_2',
        'description': 'cost > 0.01',
        'metric': {
            'name': 'claude_code.cost.usage',
            'aggregation': 'sum',
            'window': 'session',
            'op': 'gt',
            'threshold': 0.01
        },
        'issue_category': 'high_cost',
        'severity': 'high'
    }])

    # Persist a metric below the threshold
    await persist_metrics([{
        'name': 'claude_code.cost.usage',
        'value': 0.005,
        'attributes': {},
        'timestamp_unix_nano': 1700000000_000000000,
        'resource_attrs': {'session_id': 's2'}
    }])

    await asyncio.sleep(0.1)

    db = get_db()
    cur = await db.execute("SELECT rule_id FROM issues WHERE rule_id = 'cost_spike_2'")
    rows = await cur.fetchall()
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_metric_rule_dedup(fresh_db):
    set_rules([{
        'id': 'cost_spike_dedup',
        'description': 'cost > 0.01',
        'metric': {
            'name': 'claude_code.cost.usage',
            'aggregation': 'sum',
            'window': 'session',
            'op': 'gt',
            'threshold': 0.01
        },
        'issue_category': 'high_cost',
        'severity': 'high'
    }])

    # First ingest
    await persist_metrics([{
        'name': 'claude_code.cost.usage',
        'value': 0.05,
        'attributes': {},
        'timestamp_unix_nano': 1700000000_000000000,
        'resource_attrs': {'session_id': 's3'}
    }])
    await asyncio.sleep(0.05)

    # Second ingest
    await persist_metrics([{
        'name': 'claude_code.cost.usage',
        'value': 0.02,
        'attributes': {},
        'timestamp_unix_nano': 1700000001_000000000,
        'resource_attrs': {'session_id': 's3'}
    }])
    await asyncio.sleep(0.05)

    db = get_db()
    cur = await db.execute("SELECT rule_id FROM issues WHERE rule_id = 'cost_spike_dedup'")
    rows = await cur.fetchall()
    assert len(rows) == 1  # Only one issue created due to deduping


@pytest.mark.asyncio
async def test_metric_rule_sql_injection_defense(fresh_db):
    from tracea.server.detection.engine import _metric_rule_matches

    # Try an injection in the aggregation field
    bad_rule = {
        'metric': {
            'name': 'claude_code.cost.usage',
            'aggregation': "sum) FROM metrics; DROP TABLE sessions; --",
            'window': 'session',
            'op': 'gt',
            'threshold': 0.01
        }
    }

    db = get_db()
    res = await _metric_rule_matches(bad_rule, 's4', db)
    assert res is False
