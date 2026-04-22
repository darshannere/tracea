import pytest
import asyncio
from tracea.server.models import TracedEvent, EventBatch
from datetime import datetime
from uuid import uuid4


@pytest.fixture
def sample_event():
    return TracedEvent(
        event_id=str(uuid4()),
        session_id=str(uuid4()),
        agent_id="test-agent",
        sequence=1,
        timestamp=datetime.utcnow(),
        type="chat.completion",
        provider="openai",
        model="gpt-4o",
        content="Test response",
        cost_usd=0.06,
        duration_ms=35000,
    )


@pytest.fixture
def sample_error_event():
    return TracedEvent(
        event_id=str(uuid4()),
        session_id=str(uuid4()),
        agent_id="test-agent",
        sequence=2,
        timestamp=datetime.utcnow(),
        type="error",
        provider="openai",
        model="gpt-4o",
        error="Connection timeout",
    )


@pytest.fixture
def temp_rule_file(tmp_path):
    """Create a temporary detection_rules.yaml file."""
    import ruamel.yaml
    rules = [
        {
            'id': 'tool_error',
            'description': 'LLM API error',
            'condition': {'exists': 'error'},
            'issue_category': 'tool_error',
            'severity': 'high'
        },
        {
            'id': 'high_cost',
            'description': 'Cost exceeds threshold',
            'condition': {'field': 'cost_usd', 'op': 'gt', 'value': 0.05},
            'issue_category': 'high_cost',
            'severity': 'high'
        },
    ]
    yaml = ruamel.yaml.YAML()
    path = tmp_path / "detection_rules.yaml"
    with open(path, 'w') as f:
        yaml.dump({'rules': rules}, f)
    return str(path)