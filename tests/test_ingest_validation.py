"""Tests for user_id validation on event ingestion."""
import pytest
import os
import asyncio
from fastapi.testclient import TestClient
from tracea.server.main import app
from tracea.server.db import init_db, close_db


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    db_file = tmp_path / "tracea_test.db"
    monkeypatch.setattr("tracea.server.db.DB_PATH", str(db_file))
    monkeypatch.setattr("tracea.server.db._db", None)
    asyncio.run(init_db())
    yield
    asyncio.run(close_db())


@pytest.fixture
def client():
    return TestClient(app)


class TestUserIdValidation:
    """Non-empty user_ids must exist in the users table."""

    @pytest.fixture(autouse=True)
    def ensure_disabled_auth(self, monkeypatch):
        monkeypatch.setenv("TRACEA_AUTH_MODE", "disabled")
        yield

    @pytest.fixture
    def setup_user(self):
        async def _setup():
            from tracea.server.db import get_db
            db = await anext(get_db())
            await db.execute(
                "DELETE FROM users WHERE user_id = ?",
                ("darshan",),
            )
            await db.execute(
                "INSERT INTO users (user_id, name, email) VALUES (?, ?, ?)",
                ("darshan", "Darshan", "darshan@example.com"),
            )
            await db.commit()
        asyncio.run(_setup())

    def test_empty_user_id_accepted(self, client):
        """Empty user_id is allowed for backward compatibility."""
        resp = client.post("/api/v1/events", json={
            "events": [{
                "event_id": "evt-1",
                "session_id": "sess-1",
                "agent_id": "test",
                "user_id": "",
                "type": "tool_call",
                "provider": "openai",
                "timestamp": "2024-01-01T00:00:00Z",
            }]
        })
        assert resp.status_code == 200

    def test_missing_user_id_accepted(self, client):
        """Omitted user_id defaults to empty and is allowed."""
        resp = client.post("/api/v1/events", json={
            "events": [{
                "event_id": "evt-1",
                "session_id": "sess-1",
                "agent_id": "test",
                "type": "tool_call",
                "provider": "openai",
                "timestamp": "2024-01-01T00:00:00Z",
            }]
        })
        assert resp.status_code == 200

    @pytest.mark.usefixtures("setup_user")
    def test_known_user_id_accepted(self, client):
        resp = client.post("/api/v1/events", json={
            "events": [{
                "event_id": "evt-1",
                "session_id": "sess-1",
                "agent_id": "test",
                "user_id": "darshan",
                "type": "tool_call",
                "provider": "openai",
                "timestamp": "2024-01-01T00:00:00Z",
            }]
        })
        assert resp.status_code == 200

    def test_unknown_user_id_rejected(self, client):
        resp = client.post("/api/v1/events", json={
            "events": [{
                "event_id": "evt-1",
                "session_id": "sess-1",
                "agent_id": "test",
                "user_id": "unknown-user",
                "type": "tool_call",
                "provider": "openai",
                "timestamp": "2024-01-01T00:00:00Z",
            }]
        })
        assert resp.status_code == 400
        data = resp.json()
        assert data["detail"]["error"] == "unknown_user_ids"
        assert "unknown-user" in data["detail"]["unknown"]

    @pytest.mark.usefixtures("setup_user")
    def test_mixed_known_and_unknown_rejected(self, client):
        resp = client.post("/api/v1/events", json={
            "events": [
                {
                    "event_id": "evt-1",
                    "session_id": "sess-1",
                    "agent_id": "test",
                    "user_id": "darshan",
                    "type": "tool_call",
                    "provider": "openai",
                    "timestamp": "2024-01-01T00:00:00Z",
                },
                {
                    "event_id": "evt-2",
                    "session_id": "sess-1",
                    "agent_id": "test",
                    "user_id": "bogus",
                    "type": "tool_call",
                    "provider": "openai",
                    "timestamp": "2024-01-01T00:00:00Z",
                },
            ]
        })
        assert resp.status_code == 400
        data = resp.json()
        assert "bogus" in data["detail"]["unknown"]
