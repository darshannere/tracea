"""Tests for tracea brain API routes."""

import json
import pytest
from fastapi.testclient import TestClient
from tracea.server.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
async def seed_brain_entries(fresh_db):
    from tracea.server.db import get_db

    db_gen = get_db()
    db = await db_gen.__anext__()

    entries = [
        {
            "id": "wf-1",
            "user_id": "alice",
            "category": "workflow",
            "title": "Read-Edit Loop",
            "content": "Agent reads files then edits them repeatedly.",
            "confidence": 0.85,
            "source_sessions": json.dumps(["sess-a", "sess-b"]),
            "hit_count": 3,
        },
        {
            "id": "err-1",
            "user_id": "alice",
            "category": "error_fix",
            "title": "SQLite lock timeout",
            "content": "Increase busy_timeout when using WAL mode.",
            "confidence": 0.92,
            "source_sessions": json.dumps(["sess-b"]),
            "hit_count": 2,
        },
        {
            "id": "code-1",
            "user_id": "bob",
            "category": "codebase",
            "title": "db.py batch writer",
            "content": "Central event batching with asyncio lock.",
            "confidence": 0.75,
            "source_sessions": json.dumps(["sess-c"]),
            "hit_count": 1,
        },
    ]
    for e in entries:
        await db.execute(
            """
            INSERT INTO brain_entries
            (id, user_id, category, title, content, confidence, source_sessions, hit_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (e["id"], e["user_id"], e["category"], e["title"], e["content"],
             e["confidence"], e["source_sessions"], e["hit_count"]),
        )
    await db.commit()


class TestListBrainEntries:
    def test_list_all(self, client, fresh_db):
        # Need async fixture in sync test — run manually
        import asyncio
        from tracea.server.db import get_db

        async def _setup():
            db_gen = get_db()
            db = await db_gen.__anext__()
            await db.execute(
                "INSERT INTO brain_entries (id, user_id, category, title, content, confidence, source_sessions, hit_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("e1", "u1", "workflow", "T1", "C1", 0.8, '["s1"]', 1),
            )
            await db.commit()

        asyncio.run(_setup())
        resp = client.get("/api/v1/brain/entries")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["entries"]) == 1
        assert data["entries"][0]["title"] == "T1"

    def test_filter_by_category(self, client, fresh_db):
        import asyncio
        from tracea.server.db import get_db

        async def _setup():
            db_gen = get_db()
            db = await db_gen.__anext__()
            for e in [("e1", "workflow", "W1"), ("e2", "error_fix", "E1")]:
                await db.execute(
                    "INSERT INTO brain_entries (id, user_id, category, title, content, confidence, source_sessions, hit_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (e[0], "u1", e[1], e[2], "C", 0.5, '["s1"]', 1),
                )
            await db.commit()

        asyncio.run(_setup())
        resp = client.get("/api/v1/brain/entries?category=workflow")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["entries"]) == 1
        assert data["entries"][0]["category"] == "workflow"

    def test_filter_by_user_id(self, client, fresh_db):
        import asyncio
        from tracea.server.db import get_db

        async def _setup():
            db_gen = get_db()
            db = await db_gen.__anext__()
            for e in [("e1", "alice", "A1"), ("e2", "bob", "B1")]:
                await db.execute(
                    "INSERT INTO brain_entries (id, user_id, category, title, content, confidence, source_sessions, hit_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (e[0], e[1], "workflow", e[2], "C", 0.5, '["s1"]', 1),
                )
            await db.commit()

        asyncio.run(_setup())
        resp = client.get("/api/v1/brain/entries?user_id=alice")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["entries"]) == 1
        assert data["entries"][0]["user_id"] == "alice"

    def test_search_fts(self, client, fresh_db):
        import asyncio
        from tracea.server.db import get_db

        async def _setup():
            db_gen = get_db()
            db = await db_gen.__anext__()
            for e in [("e1", "SQLite WAL mode guide"), ("e2", "React hooks pattern")]:
                await db.execute(
                    "INSERT INTO brain_entries (id, user_id, category, title, content, confidence, source_sessions, hit_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (e[0], "u1", "workflow", e[1], f"Content about {e[1]}", 0.5, '["s1"]', 1),
                )
            await db.commit()

        asyncio.run(_setup())
        resp = client.get("/api/v1/brain/entries?q=SQLite")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["entries"]) == 1
        assert "SQLite" in data["entries"][0]["title"]

    def test_pagination_cursor(self, client, fresh_db):
        import asyncio
        from tracea.server.db import get_db

        async def _setup():
            db_gen = get_db()
            db = await db_gen.__anext__()
            for i in range(5):
                await db.execute(
                    "INSERT INTO brain_entries (id, user_id, category, title, content, confidence, source_sessions, hit_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (f"e{i}", "u1", "workflow", f"T{i}", "C", 0.5, '["s1"]', 5 - i),
                )
            await db.commit()

        asyncio.run(_setup())
        resp = client.get("/api/v1/brain/entries?limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["entries"]) == 2
        assert data["next_cursor"] is not None

        resp2 = client.get(f"/api/v1/brain/entries?limit=2&cursor={data['next_cursor']}")
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert len(data2["entries"]) == 2


class TestGetBrainEntry:
    def test_get_existing(self, client, fresh_db):
        import asyncio
        from tracea.server.db import get_db

        async def _setup():
            db_gen = get_db()
            db = await db_gen.__anext__()
            await db.execute(
                "INSERT INTO brain_entries (id, user_id, category, title, content, confidence, source_sessions, hit_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("e1", "u1", "workflow", "T1", "C1", 0.8, '["s1"]', 1),
            )
            await db.commit()

        asyncio.run(_setup())
        resp = client.get("/api/v1/brain/entries/e1")
        assert resp.status_code == 200
        assert resp.json()["title"] == "T1"

    def test_get_missing(self, client, fresh_db):
        resp = client.get("/api/v1/brain/entries/no-such-id")
        assert resp.status_code == 404


class TestDeleteBrainEntry:
    def test_delete_existing(self, client, fresh_db):
        import asyncio
        from tracea.server.db import get_db

        async def _setup():
            db_gen = get_db()
            db = await db_gen.__anext__()
            await db.execute(
                "INSERT INTO brain_entries (id, user_id, category, title, content, confidence, source_sessions, hit_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("e1", "u1", "workflow", "T1", "C1", 0.8, '["s1"]', 1),
            )
            await db.commit()

        asyncio.run(_setup())
        resp = client.delete("/api/v1/brain/entries/e1")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        resp2 = client.get("/api/v1/brain/entries/e1")
        assert resp2.status_code == 404

    def test_delete_missing(self, client, fresh_db):
        resp = client.delete("/api/v1/brain/entries/no-such-id")
        assert resp.status_code == 404


class TestBrainGraph:
    def test_graph_nodes_and_edges(self, client, fresh_db):
        import asyncio
        from tracea.server.db import get_db

        async def _setup():
            db_gen = get_db()
            db = await db_gen.__anext__()
            # e1 and e2 share sess-a; e3 is isolated
            entries = [
                ("e1", "u1", "workflow", "T1", "C1", 0.8, '["sess-a", "sess-b"]'),
                ("e2", "u1", "error_fix", "T2", "C2", 0.7, '["sess-a"]'),
                ("e3", "u1", "codebase", "T3", "C3", 0.6, '["sess-c"]'),
            ]
            for e in entries:
                await db.execute(
                    "INSERT INTO brain_entries (id, user_id, category, title, content, confidence, source_sessions, hit_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (e[0], e[1], e[2], e[3], e[4], e[5], e[6], 1),
                )
            await db.commit()

        asyncio.run(_setup())
        resp = client.get("/api/v1/brain/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) == 3
        # e1-e2 share sess-a, e1-e3 and e2-e3 do not
        edges = {(e["source"], e["target"]) for e in data["edges"]}
        assert ("e1", "e2") in edges or ("e2", "e1") in edges
        assert len(data["edges"]) == 1

    def test_graph_filter_user(self, client, fresh_db):
        import asyncio
        from tracea.server.db import get_db

        async def _setup():
            db_gen = get_db()
            db = await db_gen.__anext__()
            entries = [
                ("e1", "alice", "workflow", "T1", "C1", 0.8, '["sess-a"]'),
                ("e2", "bob", "workflow", "T2", "C2", 0.7, '["sess-a"]'),
            ]
            for e in entries:
                await db.execute(
                    "INSERT INTO brain_entries (id, user_id, category, title, content, confidence, source_sessions, hit_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (e[0], e[1], e[2], e[3], e[4], e[5], e[6], 1),
                )
            await db.commit()

        asyncio.run(_setup())
        resp = client.get("/api/v1/brain/graph?user_id=alice")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["id"] == "e1"

    def test_graph_filter_confidence(self, client, fresh_db):
        import asyncio
        from tracea.server.db import get_db

        async def _setup():
            db_gen = get_db()
            db = await db_gen.__anext__()
            entries = [
                ("e1", "u1", "workflow", "T1", "C1", 0.9, '["sess-a"]'),
                ("e2", "u1", "workflow", "T2", "C2", 0.3, '["sess-a"]'),
            ]
            for e in entries:
                await db.execute(
                    "INSERT INTO brain_entries (id, user_id, category, title, content, confidence, source_sessions, hit_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (e[0], e[1], e[2], e[3], e[4], e[5], e[6], 1),
                )
            await db.commit()

        asyncio.run(_setup())
        resp = client.get("/api/v1/brain/graph?min_confidence=0.5")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["id"] == "e1"
