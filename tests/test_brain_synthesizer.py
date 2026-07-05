"""Tests for tracea.server.brain.synthesizer."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tracea.server.brain.synthesizer import (
    _compress_events,
    _compute_entry_id,
    _extract_json,
    _fetch_events,
    _fetch_pending_sessions,
    _process_session,
    _upsert_entry,
    start_worker,
    stop_worker,
)
from tracea.server.brain.models import BrainEntryExtract


class TestComputeEntryId:
    def test_stable_hash(self):
        assert _compute_entry_id("error_fix", "SQLite Lock") == _compute_entry_id("error_fix", "sqlite lock")

    def test_different_categories_different_ids(self):
        assert _compute_entry_id("error_fix", "foo") != _compute_entry_id("workflow", "foo")


class TestExtractJson:
    def test_json_code_block(self):
        text = "```json\n[{\"a\": 1}]\n```"
        assert _extract_json(text) == '[{"a": 1}]'

    def test_plain_code_block(self):
        text = "Some text\n```\n[{\"a\": 1}]\n```"
        assert _extract_json(text) == '[{"a": 1}]'

    def test_raw_json(self):
        text = '[{"a": 1}]'
        assert _extract_json(text) == '[{"a": 1}]'


class TestCompressEvents:
    def test_empty(self):
        assert _compress_events([]) == "(no events)"

    def test_single_event(self):
        events = [{"sequence": 1, "type": "tool_call", "tool_name": "read", "content": "hello", "error": ""}]
        result = _compress_events(events)
        assert "seq=1" in result
        assert "tool=read" in result
        assert "hello" in result

    def test_dedup_consecutive_same_tool(self):
        events = [
            {"sequence": 1, "type": "tool_call", "tool_name": "read", "content": "a", "error": ""},
            {"sequence": 2, "type": "tool_call", "tool_name": "read", "content": "b", "error": ""},
            {"sequence": 3, "type": "tool_call", "tool_name": "read", "content": "c", "error": ""},
        ]
        result = _compress_events(events)
        assert result.count("tool=read") == 1
        assert "x3" in result

    def test_error_preserved_full(self):
        events = [
            {"sequence": 1, "type": "error", "tool_name": "", "content": "", "error": "Connection refused"},
        ]
        result = _compress_events(events)
        assert "ERROR: Connection refused" in result

    def test_truncate_long_content(self):
        events = [
            {"sequence": 1, "type": "tool_result", "tool_name": "", "content": "x" * 500, "error": ""},
        ]
        result = _compress_events(events)
        assert "..." in result
        assert len(result) < 300

    def test_sampling_large_session(self):
        events = [
            {"sequence": i, "type": "tool_call", "tool_name": f"tool{i}", "content": "", "error": ""}
            for i in range(200)
        ]
        result = _compress_events(events)
        assert "(sampled middle)" in result
        lines = result.split("\n")
        assert len(lines) < 160  # first 50 + last 50 + sampled + markers


class TestWorkerLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        await start_worker()
        await asyncio.sleep(0.1)
        await stop_worker()

    @pytest.mark.asyncio
    async def test_worker_survives_poll_cycle(self, monkeypatch):
        """Regression: the worker loop must not crash on the first poll.

        Previously the loop referenced config.enabled (no such field on
        RCABackendConfig) → AttributeError killed the worker task silently, so
        brain_status='pending' rows piled up forever. With the fix the disabled
        check uses only config.backend, and the task stays alive across polls.
        """
        import tracea.server.brain.synthesizer as synth

        # Make the loop iterate quickly
        monkeypatch.setattr(synth, "_POLL_INTERVAL", 0.01)

        await start_worker()
        try:
            # Allow several poll iterations
            await asyncio.sleep(0.1)
            # The worker task must still be alive (not killed by an exception)
            assert synth._worker_task is not None
            assert not synth._worker_task.done(), (
                f"worker died unexpectedly: {synth._worker_task.exception()!r}"
            )
        finally:
            await stop_worker()


class TestProcessSession:
    @pytest.mark.asyncio
    async def test_noise_filter_skips_small_session(self, fresh_db):
        from tracea.server.db import get_db

        db = get_db()

        # Insert a session with 2 events
        await db.execute(
            "INSERT INTO sessions (session_id, brain_status, event_count) VALUES (?, ?, ?)",
            ("sess-small", "pending", 2),
        )
        for i in range(2):
            await db.execute(
                "INSERT INTO events (event_id, session_id, sequence, timestamp, type) VALUES (?, ?, ?, ?, ?)",
                (f"evt-{i}", "sess-small", i, "2024-01-01T00:00:00Z", "tool_call"),
            )
        await db.commit()

        mock_backend = AsyncMock()
        mock_backend.analyze = AsyncMock(return_value='[{"category": "workflow", "title": "t", "content": "c", "confidence": 0.5}]')

        await _process_session(mock_backend, {"session_id": "sess-small", "user_id": ""}, None)

        # Should be marked done without calling backend (noise filter)
        db_gen = get_db()
        db2 = get_db()
        cursor = await db2.execute("SELECT brain_status FROM sessions WHERE session_id = ?", ("sess-small",))
        row = await cursor.fetchone()
        await db2.close()
        assert row["brain_status"] == "done"
        mock_backend.analyze.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_synthesis(self, fresh_db):
        from tracea.server.db import get_db

        db = get_db()

        # Insert a session with 10 events
        await db.execute(
            "INSERT INTO sessions (session_id, brain_status, event_count) VALUES (?, ?, ?)",
            ("sess-ok", "pending", 10),
        )
        for i in range(10):
            await db.execute(
                "INSERT INTO events (event_id, session_id, sequence, timestamp, type, tool_name, content, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (f"evt-{i}", "sess-ok", i, "2024-01-01T00:00:00Z", "tool_call", "read", f"content {i}", ""),
            )
        await db.commit()

        mock_backend = AsyncMock()
        mock_backend.analyze = AsyncMock(return_value='[{"category": "workflow", "title": "Read pattern", "content": "Agent reads files repeatedly", "confidence": 0.8}]')

        await _process_session(mock_backend, {"session_id": "sess-ok", "user_id": "u1"}, None)

        # Verify entry created
        db_gen = get_db()
        db2 = get_db()
        cursor = await db2.execute("SELECT * FROM brain_entries WHERE user_id = ?", ("u1",))
        row = await cursor.fetchone()
        assert row is not None
        assert row["category"] == "workflow"
        assert row["title"] == "Read pattern"
        assert row["hit_count"] == 1

        # Verify session marked done
        cursor = await db2.execute("SELECT brain_status FROM sessions WHERE session_id = ?", ("sess-ok",))
        row = await cursor.fetchone()
        await db2.close()
        assert row["brain_status"] == "done"

    @pytest.mark.asyncio
    async def test_invalid_json_marks_failed(self, fresh_db):
        from tracea.server.db import get_db

        db = get_db()

        await db.execute(
            "INSERT INTO sessions (session_id, brain_status, event_count) VALUES (?, ?, ?)",
            ("sess-bad", "pending", 10),
        )
        for i in range(10):
            await db.execute(
                "INSERT INTO events (event_id, session_id, sequence, timestamp, type, tool_name, content, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (f"evt-{i}", "sess-bad", i, "2024-01-01T00:00:00Z", "tool_call", "read", f"content {i}", ""),
            )
        await db.commit()

        mock_backend = AsyncMock()
        mock_backend.analyze = AsyncMock(return_value="not json at all")

        await _process_session(mock_backend, {"session_id": "sess-bad", "user_id": ""}, None)

        db_gen = get_db()
        db2 = get_db()
        cursor = await db2.execute("SELECT brain_status FROM sessions WHERE session_id = ?", ("sess-bad",))
        row = await cursor.fetchone()
        await db2.close()
        assert row["brain_status"] == "failed"

    @pytest.mark.asyncio
    async def test_wrong_schema_marks_failed(self, fresh_db):
        from tracea.server.db import get_db

        db = get_db()

        await db.execute(
            "INSERT INTO sessions (session_id, brain_status, event_count) VALUES (?, ?, ?)",
            ("sess-schema", "pending", 10),
        )
        for i in range(10):
            await db.execute(
                "INSERT INTO events (event_id, session_id, sequence, timestamp, type, tool_name, content, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (f"evt-{i}", "sess-schema", i, "2024-01-01T00:00:00Z", "tool_call", "read", f"content {i}", ""),
            )
        await db.commit()

        mock_backend = AsyncMock()
        mock_backend.analyze = AsyncMock(return_value='[{"foo": "bar"}]')

        await _process_session(mock_backend, {"session_id": "sess-schema", "user_id": ""}, None)

        db_gen = get_db()
        db2 = get_db()
        cursor = await db2.execute("SELECT brain_status FROM sessions WHERE session_id = ?", ("sess-schema",))
        row = await cursor.fetchone()
        await db2.close()
        assert row["brain_status"] == "failed"


class TestUpsertEntry:
    @pytest.mark.asyncio
    async def test_insert_new(self, fresh_db):
        from tracea.server.db import get_db

        db = get_db()

        extract = BrainEntryExtract(category="workflow", title="Test", content="Body", confidence=0.7)
        await _upsert_entry(db, "id1", "u1", extract, "sess-1")
        await db.commit()

        cursor = await db.execute("SELECT * FROM brain_entries WHERE id = ?", ("id1",))
        row = await cursor.fetchone()
        assert row["hit_count"] == 1
        assert row["confidence"] == 0.7
        assert json.loads(row["source_sessions"]) == ["sess-1"]

    @pytest.mark.asyncio
    async def test_reinforce_existing(self, fresh_db):
        from tracea.server.db import get_db

        db = get_db()

        extract = BrainEntryExtract(category="workflow", title="Test", content="Body", confidence=0.7)
        await _upsert_entry(db, "id1", "u1", extract, "sess-1")
        await db.commit()

        extract2 = BrainEntryExtract(category="workflow", title="Test", content="Body", confidence=0.6)
        await _upsert_entry(db, "id1", "u1", extract2, "sess-2")
        await db.commit()

        cursor = await db.execute("SELECT * FROM brain_entries WHERE id = ?", ("id1",))
        row = await cursor.fetchone()
        assert row["hit_count"] == 2
        assert row["confidence"] > 0.7  # reinforced upward
        assert set(json.loads(row["source_sessions"])) == {"sess-1", "sess-2"}


class TestBatchWriterSetsPending:
    @pytest.mark.asyncio
    async def test_new_session_gets_brain_status_pending(self, fresh_db):
        from tracea.server.db import get_db, flush_events
        from tracea.server.models import TracedEvent, TokenUsage
        from datetime import datetime, timezone
        from uuid import uuid4

        event = TracedEvent(
            event_id=str(uuid4()),
            session_id="sess-pending",
            agent_id="test-agent",
            sequence=1,
            timestamp=datetime.now(timezone.utc),
            type="tool_call",
            provider="openai",
            model="gpt-4o",
            content="test",
            tool_name="read",
        )

        from tracea.server.db import enqueue_events
        await enqueue_events([event])
        await flush_events()
        db = get_db()
        cursor = await db.execute("SELECT brain_status FROM sessions WHERE session_id = ?", ("sess-pending",))
        row = await cursor.fetchone()
        assert row is not None
        assert row["brain_status"] == "pending"
