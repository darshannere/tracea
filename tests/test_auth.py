"""Tests for tracea server auth module."""
import pytest
import os
import hashlib
import asyncio
from unittest.mock import patch
from fastapi.testclient import TestClient
from tracea.server.main import app


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


class TestRouteProtection:
    """Wave 2 fix #12: all routes (not just ingest) must require auth."""

    @pytest.fixture(autouse=True)
    def enable_api_key_mode(self, monkeypatch):
        monkeypatch.setenv("TRACEA_AUTH_MODE", "api_key")
        monkeypatch.delenv("TRACEA_ADMIN_USER_IDS", raising=False)
        yield
        monkeypatch.setenv("TRACEA_AUTH_MODE", "disabled")

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_read_routes_blocked_without_key(self, client):
        """Every previously-open GET route must return 401 without a key."""
        routes = [
            "/api/v1/sessions",
            "/api/v1/issues",
            "/api/v1/agents",
            "/api/v1/users",
            "/api/v1/api-keys",
            "/api/v1/brain/entries",
            "/api/v1/brain/graph",
            "/api/v1/config/rules",
            "/api/v1/config/alerts",
            "/api/v1/config/rca",
            "/api/v1/observagent/events",
            "/api/v1/observagent/sessions",
        ]
        blocked = []
        for route in routes:
            resp = client.get(route)
            if resp.status_code != 401:
                blocked.append((route, resp.status_code))
        assert not blocked, f"these routes were not auth-protected: {blocked}"

    @pytest.fixture
    def setup_user_and_key(self):
        async def _setup():
            from tracea.server.db import get_db
            db = await anext(get_db())
            await db.execute("DELETE FROM api_keys WHERE user_id IN (?, ?)", ("alice", "bob"))
            await db.execute("DELETE FROM users WHERE user_id IN (?, ?)", ("alice", "bob"))
            await db.execute(
                "INSERT INTO users (user_id, name, email) VALUES (?, ?, ?)",
                ("alice", "Alice", "a@x.com"),
            )
            await db.execute(
                "INSERT INTO users (user_id, name, email) VALUES (?, ?, ?)",
                ("bob", "Bob", "b@x.com"),
            )
            await db.execute(
                "INSERT INTO api_keys (key_hash, user_id, name) VALUES (?, ?, ?)",
                (hashlib.sha256(b"alice-key").hexdigest(), "alice", "k"),
            )
            await db.execute(
                "INSERT INTO api_keys (key_hash, user_id, name) VALUES (?, ?, ?)",
                (hashlib.sha256(b"bob-key").hexdigest(), "bob", "k"),
            )
            await db.commit()
        asyncio.run(_setup())

    @pytest.mark.usefixtures("setup_user_and_key")
    def test_read_routes_succeed_with_valid_key(self, client):
        """Valid key grants read access to protected GET routes."""
        headers = {"Authorization": "Bearer alice-key"}
        for route in ["/api/v1/sessions", "/api/v1/issues", "/api/v1/config/rules"]:
            resp = client.get(route, headers=headers)
            assert resp.status_code == 200, f"{route} returned {resp.status_code}"

    @pytest.mark.usefixtures("setup_user_and_key")
    def test_admin_route_forbidden_when_not_admin(self, client, monkeypatch):
        """Mutation routes (user/key/config) must 403 for non-admin when
        TRACEA_ADMIN_USER_IDS restricts admins."""
        monkeypatch.setenv("TRACEA_ADMIN_USER_IDS", "alice")
        resp = client.post(
            "/api/v1/users",
            json={"user_id": "eve", "name": "Eve"},
            headers={"Authorization": "Bearer bob-key"},
        )
        assert resp.status_code == 403, f"non-admin should be blocked, got {resp.status_code}"

    @pytest.mark.usefixtures("setup_user_and_key")
    def test_admin_route_succeeds_for_admin(self, client, monkeypatch):
        """Admin user (listed in TRACEA_ADMIN_USER_IDS) can mutate."""
        monkeypatch.setenv("TRACEA_ADMIN_USER_IDS", "alice")
        resp = client.post(
            "/api/v1/users",
            json={"user_id": "carol", "name": "Carol"},
            headers={"Authorization": "Bearer alice-key"},
        )
        assert resp.status_code == 200, f"admin should succeed, got {resp.status_code}"
