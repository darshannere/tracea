"""Test suite for all 9 seed rules in detection_rules.yaml."""
import pytest
import os
from tracea.server.detection.loader import RulesLoader


def test_all_9_seed_rules_exist_and_validate():
    """Verify all 9 seed rules from detection_rules.yaml are present and valid."""
    # Load from defaults path
    defaults_path = '/app/defaults/detection_rules.yaml'

    # Check local path for testing (during dev)
    local_path = 'tracea/server/detection/defaults/detection_rules.yaml'
    path = local_path if os.path.exists(local_path) else defaults_path

    loader = RulesLoader(path)
    rules = loader.load()

    rule_ids = {r['id'] for r in rules}
    required = {
        'tool_error', 'task_failure', 'high_cost', 'high_latency',
        'empty_response', 'model_error_5xx', 'rate_limit_hit',
        'repeated_tool_call', 'infinite_loop'
    }

    assert required.issubset(rule_ids), f"Missing rules: {required - rule_ids}"
    assert len(rules) >= 9, f"Expected at least 9 rules, got {len(rules)}"


def test_seed_rule_thresholds():
    """Verify seed rule thresholds match CONTEXT.md decisions."""
    local_path = 'tracea/server/detection/defaults/detection_rules.yaml'
    defaults_path = '/app/defaults/detection_rules.yaml'
    path = local_path if os.path.exists(local_path) else defaults_path

    loader = RulesLoader(path)
    rules = loader.load()
    rules_dict = {r['id']: r for r in rules}

    assert rules_dict['high_cost']['condition']['value'] == 0.05
    assert rules_dict['high_latency']['condition']['value'] == 30000
    assert rules_dict['repeated_tool_call']['repetition']['min_count'] == 5
    assert rules_dict['infinite_loop']['repetition']['min_count'] == 10


def test_empty_response_fires_on_both_event_types():
    """Verify empty_response rule has OR condition covering both chat.completion and tool_result."""
    local_path = 'tracea/server/detection/defaults/detection_rules.yaml'
    defaults_path = '/app/defaults/detection_rules.yaml'
    path = local_path if os.path.exists(local_path) else defaults_path

    loader = RulesLoader(path)
    rules = loader.load()
    rules_dict = {r['id']: r for r in rules}
    er_rule = rules_dict['empty_response']

    # condition should have 'or' at top level (serialized as 'or_' by Pydantic)
    assert 'or_' in er_rule['condition'], \
        f"empty_response rule missing 'or' condition: {er_rule['condition']}"


def test_tool_error_rule_exists():
    """Verify tool_error rule exists and has correct structure."""
    local_path = 'tracea/server/detection/defaults/detection_rules.yaml'
    defaults_path = '/app/defaults/detection_rules.yaml'
    path = local_path if os.path.exists(local_path) else defaults_path

    loader = RulesLoader(path)
    rules = loader.load()
    rules_dict = {r['id']: r for r in rules}

    te = rules_dict['tool_error']
    assert te['severity'] == 'high'
    assert te['issue_category'] == 'tool_error'
    assert 'exists' in te['condition']
    assert te['condition']['exists'] == 'error'


def test_task_failure_rule_type_check():
    """Verify task_failure rule checks for type='error'."""
    local_path = 'tracea/server/detection/defaults/detection_rules.yaml'
    defaults_path = '/app/defaults/detection_rules.yaml'
    path = local_path if os.path.exists(local_path) else defaults_path

    loader = RulesLoader(path)
    rules = loader.load()
    rules_dict = {r['id']: r for r in rules}

    tf = rules_dict['task_failure']
    assert tf['severity'] == 'critical'
    assert tf['condition']['field'] == 'type'
    assert tf['condition']['op'] == 'equals'
    assert tf['condition']['value'] == 'error'


def test_model_error_5xx_composite_and():
    """Verify model_error_5xx uses AND composite for 500 <= status_code < 600."""
    local_path = 'tracea/server/detection/defaults/detection_rules.yaml'
    defaults_path = '/app/defaults/detection_rules.yaml'
    path = local_path if os.path.exists(local_path) else defaults_path

    loader = RulesLoader(path)
    rules = loader.load()
    rules_dict = {r['id']: r for r in rules}

    me = rules_dict['model_error_5xx']
    assert me['severity'] == 'high'
    # condition has 'and' at top level (serialized as 'and_')
    assert 'and_' in me['condition']
    and_conds = me['condition']['and_']
    assert len(and_conds) == 2
    # Should have gte 500 and lt 600
    ops = {c['op'] for c in and_conds}
    vals = {c['value'] for c in and_conds}
    assert 'gte' in ops and 'lt' in ops
    assert 500 in vals and 600 in vals


def test_rate_limit_hit_status_code_429():
    """Verify rate_limit_hit checks for status_code == 429."""
    local_path = 'tracea/server/detection/defaults/detection_rules.yaml'
    defaults_path = '/app/defaults/detection_rules.yaml'
    path = local_path if os.path.exists(local_path) else defaults_path

    loader = RulesLoader(path)
    rules = loader.load()
    rules_dict = {r['id']: r for r in rules}

    rl = rules_dict['rate_limit_hit']
    assert rl['severity'] == 'high'
    assert rl['condition']['field'] == 'status_code'
    assert rl['condition']['op'] == 'eq'
    assert rl['condition']['value'] == 429