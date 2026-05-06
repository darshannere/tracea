import pytest
import asyncio
import os
from tracea.server.models import TracedEvent, EventBatch
from tracea.server.db import init_db, close_db
from datetime import datetime
from uuid import uuid4


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Initialize a fresh in-memory database for each test."""
    db_file = tmp_path / "tracea_test.db"
    monkeypatch.setattr("tracea.server.db.DB_PATH", str(db_file))
    monkeypatch.setattr("tracea.server.db._db", None)
    asyncio.run(init_db())
    yield
    asyncio.run(close_db())


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