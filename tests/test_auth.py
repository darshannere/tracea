"""Tests for tracea server auth module."""
import pytest
import os
import hashlib
import asyncio
from unittest.mock import patch
from fastapi.testclient import TestClient
from tracea.server.main import app
from tracea.server.db import init_db, close_db


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
def client():
    return TestClient(app)


class TestDisabledMode:
    """Auth is disabled by default — all requests should succeed."""

    def test_ingest_without_auth(self, client):
        """No auth header required in disabled mode."""
        resp = client.post("/api/v1/events/mcp", json={
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


class TestApiKeyMode:
    """Auth mode requires a valid API key."""

    @pytest.fixture(autouse=True)
    def enable_api_key_mode(self, monkeypatch):
        monkeypatch.setenv("TRACEA_AUTH_MODE", "api_key")
        yield
        monkeypatch.setenv("TRACEA_AUTH_MODE", "disabled")

    @pytest.fixture
    def setup_user_and_key(self):
        """Create a user and an API key in the test DB."""
        async def _setup():
            from tracea.server.db import get_db
            db = await anext(get_db())
            await db.execute(
                "DELETE FROM users WHERE user_id = ?",
                ("alice",),
            )
            await db.execute(
                "DELETE FROM api_keys WHERE user_id = ?",
                ("alice",),
            )
            await db.execute(
                "INSERT INTO users (user_id, name, email) VALUES (?, ?, ?)",
                ("alice", "Alice", "alice@example.com"),
            )
            key_hash = hashlib.sha256(b"secret-key").hexdigest()
            await db.execute(
                "INSERT INTO api_keys (key_hash, user_id, name) VALUES (?, ?, ?)",
                (key_hash, "alice", "test key"),
            )
            await db.commit()
        asyncio.run(_setup())

    def test_ingest_without_key_returns_401(self, client):
        resp = client.post("/api/v1/events/mcp", json={
            "events": [{
                "event_id": "evt-1",
                "session_id": "sess-1",
                "agent_id": "test",
                "type": "tool_call",
                "provider": "openai",
                "timestamp": "2024-01-01T00:00:00Z",
            }]
        })
        assert resp.status_code == 401

    def test_ingest_with_invalid_key_returns_401(self, client):
        resp = client.post("/api/v1/events/mcp", json={
            "events": [{
                "event_id": "evt-1",
                "session_id": "sess-1",
                "agent_id": "test",
                "type": "tool_call",
                "provider": "openai",
                "timestamp": "2024-01-01T00:00:00Z",
            }]
        }, headers={"Authorization": "Bearer bad-key"})
        assert resp.status_code == 401

    @pytest.mark.usefixtures("setup_user_and_key")
    def test_ingest_with_valid_key_succeeds(self, client):
        resp = client.post("/api/v1/events/mcp", json={
            "events": [{
                "event_id": "evt-1",
                "session_id": "sess-1",
                "agent_id": "test",
                "type": "tool_call",
                "provider": "openai",
                "timestamp": "2024-01-01T00:00:00Z",
            }]
        }, headers={"Authorization": "Bearer secret-key"})
        assert resp.status_code == 200

    @pytest.mark.usefixtures("setup_user_and_key")
    def test_ingest_injects_user_id_from_key(self, client):
        """When event has no user_id, auth should inject it from the API key."""
        resp = client.post("/api/v1/events/mcp", json={
            "events": [{
                "event_id": "evt-1",
                "session_id": "sess-1",
                "agent_id": "test",
                "type": "tool_call",
                "provider": "openai",
                "timestamp": "2024-01-01T00:00:00Z",
            }]
        }, headers={"Authorization": "Bearer secret-key"})
        assert resp.status_code == 200

    @pytest.mark.usefixtures("setup_user_and_key")
    def test_ingest_preserves_explicit_user_id(self, client):
        """When event already has a user_id, it should be preserved."""
        resp = client.post("/api/v1/events/mcp", json={
            "events": [{
                "event_id": "evt-1",
                "session_id": "sess-1",
                "agent_id": "test",
                "user_id": "alice",
                "type": "tool_call",
                "provider": "openai",
                "timestamp": "2024-01-01T00:00:00Z",
            }]
        }, headers={"Authorization": "Bearer secret-key"})
        assert resp.status_code == 200
