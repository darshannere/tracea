"""Tests for OTLP/HTTP ingestion: parser, routes, mapper, auth."""
import json
import os
import asyncio
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tracea.server.main import app
from tracea.server.db import init_db, close_db

FIXTURES = Path(__file__).parent / "fixtures"


# ---------- shared fixtures (local — not relying on conftest's fresh_db) ----------

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


@pytest.fixture(autouse=True)
def dev_mode(monkeypatch):
    """Default to disabled auth + capture content on."""
    monkeypatch.setenv("TRACEA_AUTH_MODE", "disabled")
    monkeypatch.setenv("TRACEA_CAPTURE_CONTENT", "1")
    yield


def _load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _read_db(query, args=()):
    import sqlite3
    from tracea.server.db import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(query, args).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------- parser unit tests ----------

class TestParser:
    def test_parse_traces_json_empty(self):
        from tracea.server.otel.parser import parse_traces
        assert parse_traces(b"{}", "application/json") == []

    def test_parse_traces_json_three_spans(self):
        from tracea.server.otel.parser import parse_traces
        body = _load("otlp-traces-request.json")
        spans = parse_traces(body, "application/json")
        assert len(spans) == 3
        names = [s["name"] for s in spans]
        assert "claude_code.interaction" in names
        # parent linking
        tool_span = next(s for s in spans if s["span_id"] == "2222222222222222")
        assert tool_span["parent_span_id"] == "1111111111111111"
        # span-level + resource attributes propagated
        assert spans[0]["span_attrs"]["session.id"] == "claude-sess-001"
        assert spans[0]["resource_attrs"]["service.name"] == "claude-code"
        # trace_id hex string
        assert len(spans[0]["trace_id"]) == 32

    def test_parse_traces_protobuf(self):
        from tracea.server.otel.parser import parse_traces
        from opentelemetry.proto.collector.trace.v1 import trace_service_pb2 as tpb
        # Populate the proto message from the JSON fixture, then reserialize.
        # Note: the fixture's traceId/spanId are hex (OTLP/JSON convention);
        # convert to base64 before ParseDict, same as the parser does.
        from google.protobuf.json_format import ParseDict
        from tracea.server.otel.parser import _hex_ids_to_base64
        req = tpb.ExportTraceServiceRequest()
        body = json.loads(_load("otlp-traces-request.json"))
        _hex_ids_to_base64(body)
        ParseDict(body, req)
        proto_bytes = req.SerializeToString()
        spans = parse_traces(proto_bytes, "application/x-protobuf")
        assert len(spans) == 3
        assert spans[0]["span_attrs"]["session.id"] == "claude-sess-001"

    def test_parse_logs_json_claude_code(self):
        from tracea.server.otel.parser import parse_logs
        logs = parse_logs(_load("otlp-logs-claude-code.json"), "application/json")
        assert len(logs) == 1
        log = logs[0]
        assert log["scope_name"] == "claude-code"
        assert log["trace_id"] == "abcdef0123456789abcdef0123456789"
        assert "msg_01ABC" in log["body"]  # the JSON body string
        assert log["log_attrs"]["event.name"] == "claude_code.api_response_body"

    def test_parse_logs_json_genai_gemini(self):
        from tracea.server.otel.parser import parse_logs
        logs = parse_logs(_load("otlp-logs-genai-gemini.json"), "application/json")
        assert len(logs) == 1
        log = logs[0]
        attrs = log["log_attrs"]
        assert attrs["event.name"] == "gen_ai.client.inference.operation.details"
        assert isinstance(attrs["gen_ai.input.messages"], list)
        assert len(attrs["gen_ai.input.messages"]) == 1
        # nested parts accessible
        msg = attrs["gen_ai.input.messages"][0]
        assert msg["role"] == "user"

    def test_parse_metrics_json(self):
        from tracea.server.otel.parser import parse_metrics
        metrics = parse_metrics(_load("otlp-metrics-request.json"), "application/json")
        assert len(metrics) == 2
        names = {m["name"] for m in metrics}
        assert "gen_ai.client.token.usage" in names
        assert "claude_code.cost.usage" in names
        tok = next(m for m in metrics if m["name"] == "gen_ai.client.token.usage")
        assert tok["value"] == 523.0


# ---------- mapper unit tests ----------

class TestMapperClaudeCode:
    def test_api_response_body_maps_to_chat_completion(self):
        from tracea.server.otel.parser import parse_logs
        from tracea.server.otel.mapper import logs_to_events
        logs = parse_logs(_load("otlp-logs-claude-code.json"), "application/json")
        events = logs_to_events(logs, user_id="u1")
        assert len(events) == 1
        e = events[0]
        assert e.type == "chat.completion"
        assert e.role == "assistant"
        assert e.content == "Hello! How can I help?"
        assert e.model == "claude-sonnet-5-20250929"
        assert e.tokens_used.input == 15
        assert e.tokens_used.output == 7
        assert e.tokens_used.total == 22
        assert e.cost_usd is not None and e.cost_usd > 0
        assert e.provider == "claude-code"
        assert e.session_id == "claude-sess-001"

    def test_capture_content_disabled_strips_content(self, monkeypatch):
        monkeypatch.setenv("TRACEA_CAPTURE_CONTENT", "0")
        from tracea.server.otel.parser import parse_logs
        from tracea.server.otel.mapper import logs_to_events
        logs = parse_logs(_load("otlp-logs-claude-code.json"), "application/json")
        events = logs_to_events(logs)
        assert events[0].content is None
        # raw_body should also be absent from metadata
        assert "raw_body" not in events[0].metadata


class TestMapperGemini:
    def test_genai_event_produces_per_message_events(self):
        from tracea.server.otel.parser import parse_logs
        from tracea.server.otel.mapper import logs_to_events
        logs = parse_logs(_load("otlp-logs-genai-gemini.json"), "application/json")
        events = logs_to_events(logs, user_id="u1")
        # Expect: 1 system + 1 input user + 1 output (model→assistant) = 3
        assert len(events) == 3
        roles = [e.role for e in events]
        assert roles == ["system", "user", "assistant"], roles
        assert events[0].content == "You are Gemini CLI."
        assert events[1].content == "explain this code"
        assert events[2].content == "This code does X and Y."
        assert events[0].provider == "gemini-cli"
        assert events[0].model == "gemini-2.5-pro"
        assert events[2].tokens_used.total == 129  # 42 + 87


# ---------- end-to-end route tests ----------

class TestOTLPRoutes:
    def test_empty_json_logs_returns_200(self, client):
        resp = client.post("/v1/logs", json={}, headers={"Content-Type": "application/json"})
        assert resp.status_code == 200

    def test_empty_proto_traces_returns_200(self, client):
        resp = client.post("/v1/traces", content=b"",
                           headers={"Content-Type": "application/x-protobuf"})
        assert resp.status_code == 200

    def test_post_claude_code_logs_creates_event(self, client):
        body = _load("otlp-logs-claude-code.json")
        resp = client.post("/v1/logs", content=body,
                           headers={"Content-Type": "application/json"})
        assert resp.status_code == 200

        # Confirm the event landed in the DB
        rows = _read_db(
            "SELECT type, role, content, model FROM events WHERE provider = 'claude-code'"
        )
        assert len(rows) == 1
        assert rows[0]["role"] == "assistant"
        assert "Hello! How can I help?" in rows[0]["content"]
        assert rows[0]["model"] == "claude-sonnet-5-20250929"

    def test_post_genai_logs_creates_events(self, client):
        body = _load("otlp-logs-genai-gemini.json")
        resp = client.post("/v1/logs", content=body,
                           headers={"Content-Type": "application/json"})
        assert resp.status_code == 200

        rows = _read_db(
            "SELECT role FROM events WHERE provider='gemini-cli' ORDER BY timestamp"
        )
        roles = [r["role"] for r in rows]
        assert roles == ["system", "user", "assistant"]

    def test_post_traces_persists_spans_and_tool_events(self, client):
        body = _load("otlp-traces-request.json")
        resp = client.post("/v1/traces", content=body,
                           headers={"Content-Type": "application/json"})
        assert resp.status_code == 200

        rows_spans = _read_db("SELECT COUNT(*) AS c FROM spans")
        assert rows_spans[0]["c"] == 3
        # claude_code.* spans are suppressed from the tool timeline (hooks own it);
        # session.id is carried in span-level attributes, not resource attributes.
        tool_rows = _read_db("SELECT type FROM events WHERE type LIKE 'tool%'")
        assert len(tool_rows) == 0
        sess_rows = _read_db("SELECT DISTINCT session_id FROM spans")
        assert sess_rows == [{"session_id": "claude-sess-001"}]

    def test_post_traces_genai_tool_spans_emit_events(self, client):
        body = _load("otlp-traces-genai-tools.json")
        resp = client.post("/v1/traces", content=body,
                           headers={"Content-Type": "application/json"})
        assert resp.status_code == 200

        rows_spans = _read_db("SELECT COUNT(*) AS c FROM spans")
        assert rows_spans[0]["c"] == 2
        tool_rows = _read_db(
            "SELECT type FROM events WHERE type LIKE 'tool%' ORDER BY timestamp, type"
        )
        assert len(tool_rows) == 4
        assert [r["type"] for r in tool_rows] == [
            "tool_call", "tool_call", "tool_result", "tool_result"
        ]

    def test_post_metrics_persists_rows(self, client):
        body = _load("otlp-metrics-request.json")
        resp = client.post("/v1/metrics", content=body,
                           headers={"Content-Type": "application/json"})
        assert resp.status_code == 200

        rows = _read_db("SELECT name, value FROM metrics ORDER BY name")
        assert len(rows) == 2

    def test_metrics_idempotent_on_repost(self, client):
        body = _load("otlp-metrics-request.json")
        client.post("/v1/metrics", content=body, headers={"Content-Type": "application/json"})
        client.post("/v1/metrics", content=body, headers={"Content-Type": "application/json"})

        rows = _read_db("SELECT COUNT(*) AS c FROM metrics")
        assert rows[0]["c"] == 2  # not 4


# ---------- auth tests ----------

class TestOTLPAuth:
    def test_dev_mode_allows_unauthenticated(self, client, monkeypatch):
        monkeypatch.setenv("TRACEA_DEV_MODE", "1")
        monkeypatch.setenv("TRACEA_AUTH_MODE", "api_key")  # even in api_key mode
        resp = client.post("/v1/logs", json={})
        assert resp.status_code == 200

    def test_api_key_mode_rejects_missing_token(self, client, monkeypatch):
        monkeypatch.delenv("TRACEA_DEV_MODE", raising=False)
        monkeypatch.setenv("TRACEA_AUTH_MODE", "api_key")
        resp = client.post("/v1/logs", json={})
        assert resp.status_code == 401

    def test_api_key_mode_accepts_valid_bearer(self, client, monkeypatch):
        monkeypatch.delenv("TRACEA_DEV_MODE", raising=False)
        monkeypatch.setenv("TRACEA_AUTH_MODE", "api_key")
        
        # Insert a key directly using sqlite3 to avoid any connection conflicts
        import sqlite3
        from tracea.server.db import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM users WHERE user_id='u1'")
        conn.execute(
            "INSERT INTO users (user_id, name) VALUES ('u1','Test')"
        )
        token = "sk-tracea-test-001"
        key_hash = hashlib.sha256(token.encode()).hexdigest()
        conn.execute("DELETE FROM api_keys WHERE key_hash=?", (key_hash,))
        conn.execute(
            "INSERT INTO api_keys (key_hash, user_id, name) VALUES (?,?,?)",
            (key_hash, "u1", "test"),
        )
        conn.commit()
        conn.close()

        resp = client.post("/v1/logs", json={},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
