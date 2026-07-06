"""Regression test for GET /api/v1/events filters.

The session/user filters are injected inside plain `FROM events` scopes —
a `tc.` alias prefix (or wrong param order) 500s or returns wrong rows.
"""
import pytest
from fastapi.testclient import TestClient
from tracea.server.main import app
from tracea.server.db import get_db


async def _seed(db):
    for eid, sid, uid, typ, tcid in [
        ("e1", "sess_a", "alice", "tool_call", "tc1"),
        ("e2", "sess_a", "alice", "tool_result", "tc1"),
        ("e3", "sess_b", "bob", "tool_call", "tc2"),
    ]:
        await db.execute(
            """INSERT INTO events
               (event_id, session_id, agent_id, user_id, sequence, timestamp,
                type, provider, model, tool_call_id, tool_name)
               VALUES (?, ?, 'a', ?, 0, '2024-01-01T00:00:00Z', ?, 'openai', '', ?, 'Bash')""",
            (eid, sid, uid, typ, tcid),
        )
    await db.commit()


@pytest.mark.asyncio
async def test_events_filter_by_session(fresh_db):
    client = TestClient(app)
    await _seed(get_db())
    resp = client.get("/api/v1/events", params={"session_id": "sess_a"})
    assert resp.status_code == 200
    events = resp.json()
    assert events and all(e["session_id"] == "sess_a" for e in events)


@pytest.mark.asyncio
async def test_events_filter_by_session_and_user(fresh_db):
    client = TestClient(app)
    await _seed(get_db())
    resp = client.get(
        "/api/v1/events", params={"session_id": "sess_a", "user_id": "alice"}
    )
    assert resp.status_code == 200
    events = resp.json()
    assert events and all(e["session_id"] == "sess_a" for e in events)

    # Mismatched pair must return nothing (catches swapped param binding)
    resp = client.get(
        "/api/v1/events", params={"session_id": "sess_a", "user_id": "bob"}
    )
    assert resp.status_code == 200
    assert resp.json() == []
