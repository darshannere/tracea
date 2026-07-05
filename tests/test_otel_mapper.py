import os
import json
import pytest
from datetime import datetime, timezone
from tracea.server.otel.mapper import logs_to_events


def test_is_claude_code_detection():
    # Detect via scope_name
    log1 = {"scope_name": "claude-code"}
    # Detect via event.name starting with claude_code.
    log2 = {"log_attrs": {"event.name": "claude_code.user_prompt"}}
    # Neither
    log3 = {"scope_name": "other-scope", "log_attrs": {"event.name": "other_event"}}

    events1 = logs_to_events([log1])
    assert len(events1) == 1
    assert events1[0].provider == "claude-code"

    events2 = logs_to_events([log2])
    assert len(events2) == 1
    assert events2[0].provider == "claude-code"

    events3 = logs_to_events([log3])
    # log3 is not detected as Claude Code, and Task 5 isn't done yet, so it won't map or will return empty/ignored
    assert len(events3) == 0


def test_claude_code_user_prompt(monkeypatch):
    monkeypatch.setenv("TRACEA_CAPTURE_CONTENT", "1")
    log = {
        "scope_name": "claude-code",
        "body": "Hello Claude",
        "log_attrs": {"event.name": "claude_code.user_prompt"},
        "resource_attrs": {"session_id": "sess-123", "agent_id": "agent-abc"},
        "timestamp_unix_nano": 1700000000_000000000,
    }
    events = logs_to_events([log])
    assert len(events) == 1
    e = events[0]
    assert e.type == "chat.completion"
    assert e.role == "user"
    assert e.content == "Hello Claude"
    assert e.session_id == "sess-123"
    assert e.agent_id == "agent-abc"
    assert e.provider == "claude-code"

    # With capture content disabled
    monkeypatch.setenv("TRACEA_CAPTURE_CONTENT", "0")
    events = logs_to_events([log])
    assert len(events) == 1
    assert events[0].content is None


def test_claude_code_assistant_response(monkeypatch):
    monkeypatch.setenv("TRACEA_CAPTURE_CONTENT", "1")
    log = {
        "scope_name": "claude-code",
        "body": "Hello human",
        "log_attrs": {"event.name": "claude_code.assistant_response"},
        "resource_attrs": {"session_id": "sess-123"},
    }
    events = logs_to_events([log])
    assert len(events) == 1
    e = events[0]
    assert e.type == "chat.completion"
    assert e.role == "assistant"
    assert e.content == "Hello human"
    assert e.session_id == "sess-123"

    monkeypatch.setenv("TRACEA_CAPTURE_CONTENT", "0")
    events = logs_to_events([log])
    assert len(events) == 1
    assert events[0].content is None


def test_claude_code_api_request_body(monkeypatch):
    monkeypatch.setenv("TRACEA_CAPTURE_CONTENT", "1")
    req_payload = {
        "model": "claude-3-5-sonnet",
        "messages": [
            {"role": "user", "content": "First prompt"},
            {"role": "assistant", "content": "First response"},
            {"role": "user", "content": [{"type": "text", "text": "Second prompt text"}]},
        ],
    }
    log = {
        "scope_name": "claude-code",
        "body": json.dumps(req_payload),
        "log_attrs": {"event.name": "claude_code.api_request_body"},
        "resource_attrs": {"session_id": "sess-123"},
    }
    events = logs_to_events([log])
    assert len(events) == 1
    e = events[0]
    assert e.type == "chat.completion"
    assert e.role == "user"
    assert e.content == "Second prompt text"
    assert e.model == "claude-3-5-sonnet"
    assert e.metadata["request_model"] == "claude-3-5-sonnet"
    assert e.metadata["raw_body"] == req_payload

    # With TRACEA_CAPTURE_CONTENT = 0
    monkeypatch.setenv("TRACEA_CAPTURE_CONTENT", "0")
    events = logs_to_events([log])
    assert len(events) == 1
    e = events[0]
    assert e.content is None
    assert "raw_body" not in e.metadata
    assert e.model == "claude-3-5-sonnet"


def test_claude_code_api_response_body(monkeypatch):
    monkeypatch.setenv("TRACEA_CAPTURE_CONTENT", "1")
    resp_payload = {
        "id": "msg_123",
        "model": "claude-3-5-sonnet",
        "content": [
            {"type": "text", "text": "Hello, how can I"},
            {"type": "text", "text": " help you?"},
        ],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }
    log = {
        "scope_name": "claude-code",
        "body": json.dumps(resp_payload),
        "log_attrs": {"event.name": "claude_code.api_response_body"},
        "resource_attrs": {"session_id": "sess-123"},
    }
    events = logs_to_events([log])
    assert len(events) == 1
    e = events[0]
    assert e.type == "chat.completion"
    assert e.role == "assistant"
    assert e.content == "Hello, how can I\n help you?"
    assert e.model == "claude-3-5-sonnet"
    assert e.tokens_used is not None
    assert e.tokens_used.input == 100
    assert e.tokens_used.output == 50
    assert e.tokens_used.total == 150
    assert e.cost_usd == pytest.approx(150 * 0.00001)
    assert e.metadata["response_id"] == "msg_123"
    assert e.metadata["stop_reason"] == "end_turn"
    assert e.metadata["raw_body"] == resp_payload

    # With TRACEA_CAPTURE_CONTENT = 0
    monkeypatch.setenv("TRACEA_CAPTURE_CONTENT", "0")
    events = logs_to_events([log])
    assert len(events) == 1
    e = events[0]
    assert e.content is None
    assert "raw_body" not in e.metadata


def test_claude_code_tool_result(monkeypatch):
    monkeypatch.setenv("TRACEA_CAPTURE_CONTENT", "1")
    log = {
        "scope_name": "claude-code",
        "body": "tool output text",
        "log_attrs": {
            "event.name": "claude_code.tool_result",
            "tool_name": "bash_tool",
        },
        "resource_attrs": {"session_id": "sess-123"},
    }
    events = logs_to_events([log])
    assert len(events) == 1
    e = events[0]
    assert e.type == "tool_result"
    assert e.tool_name == "bash_tool"
    assert e.content == "tool output text"

    # Alternate tool_name key
    log["log_attrs"] = {
        "event.name": "claude_code.tool_result",
        "gen_ai.tool.name": "alternate_tool",
    }
    events = logs_to_events([log])
    assert len(events) == 1
    assert events[0].tool_name == "alternate_tool"


def test_claude_code_api_error_refusal():
    log1 = {
        "scope_name": "claude-code",
        "body": "connection error",
        "log_attrs": {"event.name": "claude_code.api_error"},
        "resource_attrs": {"session_id": "sess-123"},
    }
    log2 = {
        "scope_name": "claude-code",
        "body": "refused to answer",
        "log_attrs": {"event.name": "claude_code.api_refusal"},
        "resource_attrs": {"session_id": "sess-123"},
    }
    events = logs_to_events([log1, log2])
    assert len(events) == 2
    assert events[0].type == "error"
    assert events[0].error == "connection error"
    assert events[1].type == "error"
    assert events[1].error == "refused to answer"


def test_fallback_session_id():
    # Falls back to trace_id
    log_trace = {
        "scope_name": "claude-code",
        "trace_id": "mytrace123",
        "log_attrs": {"event.name": "claude_code.user_prompt"},
    }
    events = logs_to_events([log_trace])
    assert events[0].session_id == "trace-mytrace123"

    # Falls back to unknown-uuid
    log_unknown = {
        "scope_name": "claude-code",
        "log_attrs": {"event.name": "claude_code.user_prompt"},
    }
    events = logs_to_events([log_unknown])
    assert events[0].session_id.startswith("unknown-")


def test_mapper_robustness():
    # Malformed body JSON should not crash
    log = {
        "scope_name": "claude-code",
        "body": "{invalid json",
        "log_attrs": {"event.name": "claude_code.api_request_body"},
    }
    events = logs_to_events([log])
    assert len(events) == 1
    assert events[0].type == "chat.completion"  # Default fallback parsed body is empty dict

    # Missing fields / unexpected types
    log2 = {
        "scope_name": "claude-code",
        "body": None,
        "log_attrs": {"event.name": "claude_code.api_request_body"},
    }
    events2 = logs_to_events([log2])
    assert len(events2) == 1

    # Completely malformed structure resulting in Exception should be caught and returned as error event
    log_bad = None
    events_bad = logs_to_events([log_bad])
    assert len(events_bad) == 1
    assert events_bad[0].type == "error"
    assert "OTLP log mapping failed" in events_bad[0].error


def test_is_genai_inference_detection():
    # Detect via event.name
    log1 = {"log_attrs": {"event.name": "gen_ai.client.inference.operation.details"}}
    log2 = {"log_attrs": {"event.name": "other_event"}}

    events1 = logs_to_events([log1])
    assert len(events1) == 1
    assert events1[0].metadata["event.name"] == "gen_ai.client.inference.operation.details"

    events2 = logs_to_events([log2])
    assert len(events2) == 0


def test_genai_inference_mapping(monkeypatch):
    monkeypatch.setenv("TRACEA_CAPTURE_CONTENT", "1")
    log = {
        "scope_name": "io.opentelemetry.contrib.genai",
        "timestamp_unix_nano": 1700000000_000000000,
        "body": "",
        "resource_attrs": {
            "gen_ai.system": "gemini",
            "session.id": "gem-sess-1",
        },
        "log_attrs": {
            "event.name": "gen_ai.client.inference.operation.details",
            "gen_ai.request.model": "gemini-2.5-pro",
            "gen_ai.usage.input_tokens": 42,
            "gen_ai.usage.output_tokens": 87,
            "gen_ai.system_instructions": "You are Gemini CLI.",
            "gen_ai.input.messages": [
                {"role": "user", "parts": [{"type": "text", "text": "hello"}]},
                {"role": "user", "parts": [{"type": "text", "text": "how are you?"}]},
            ],
            "gen_ai.output.messages": [
                {"role": "assistant", "parts": [{"type": "text", "text": "Hi! I am doing well."}]},
            ],
        },
    }
    events = logs_to_events([log], user_id="u1")
    assert len(events) == 4
    assert [e.role for e in events] == ["system", "user", "user", "assistant"]
    assert events[0].content == "You are Gemini CLI."
    assert events[1].content == "hello"
    assert events[2].content == "how are you?"
    assert events[3].content == "Hi! I am doing well."

    for e in events:
        assert e.provider == "gemini-cli"
        assert e.model == "gemini-2.5-pro"
        assert e.session_id == "gem-sess-1"
        assert e.user_id == "u1"
        assert e.tokens_used is not None
        assert e.tokens_used.input == 42
        assert e.tokens_used.output == 87
        assert e.tokens_used.total == 129
        assert e.cost_usd == pytest.approx(129 * 0.00001)

    # TRACEA_CAPTURE_CONTENT = 0 gates content and skips system_instructions emission entirely
    monkeypatch.setenv("TRACEA_CAPTURE_CONTENT", "0")
    events = logs_to_events([log], user_id="u1")
    assert len(events) == 3  # No system instructions event since content was skipped
    assert [e.role for e in events] == ["user", "user", "assistant"]
    for e in events:
        assert e.content is None


def test_genai_role_normalization():
    from tracea.server.otel.mapper import _normalize_role
    assert _normalize_role("model") == "assistant"
    assert _normalize_role("bot") == "assistant"
    assert _normalize_role("user") == "user"
    assert _normalize_role("system") == "system"
    assert _normalize_role("unknown-role") == "user"


def test_genai_empty_messages():
    log = {
        "scope_name": "genai",
        "log_attrs": {"event.name": "gen_ai.client.inference.operation.details"},
        "resource_attrs": {},
        "timestamp_unix_nano": 0,
    }
    events = logs_to_events([log])
    assert len(events) == 1
    assert events[0].content is None
    assert events[0].provider == "unknown"


def test_genai_provider_mapping():
    from tracea.server.otel.mapper import _genai_provider
    assert _genai_provider({"gen_ai.system": "gemini"}, {}) == "gemini-cli"
    assert _genai_provider({"gen_ai.system": "google"}, {}) == "gemini-cli"
    assert _genai_provider({"gen_ai.system": "anthropic"}, {}) == "claude-code"
    assert _genai_provider({"gen_ai.system": "openai"}, {}) == "openai"
    assert _genai_provider({}, {"gen_ai.system": "ollama"}) == "ollama"
    assert _genai_provider({}, {"gen_ai.system": "unknown-sys"}) == "unknown"


@pytest.mark.asyncio
async def test_spans_to_events_and_persist():
    from tracea.server.otel.mapper import spans_to_events_and_persist
    from tracea.server.db import get_db

    spans = [
        {
            'trace_id': 't1',
            'span_id': 'a',
            'parent_span_id': '',
            'name': 'claude_code.interaction',
            'kind': 1,
            'start_time_unix_nano': 1700000000_000000000,
            'end_time_unix_nano': 1700000001_000000000,
            'resource_attrs': {'session_id': 's1', 'gen_ai.system': 'anthropic'},
            'scope_name': 'claude-code',
            'span_attrs': {'gen_ai.operation.name': 'chat', 'gen_ai.request.model': 'claude-sonnet-5'}
        },
        {
            'trace_id': 't1',
            'span_id': 'b',
            'parent_span_id': 'a',
            'name': 'claude_code.tool Bash',
            'kind': 3,
            'start_time_unix_nano': 1700000000_500000000,
            'end_time_unix_nano': 1700000000_900000000,
            'resource_attrs': {'session_id': 's1'},
            'scope_name': 'claude-code',
            'span_attrs': {'gen_ai.operation.name': 'execute_tool', 'gen_ai.tool.call.id': 'tc-1', 'gen_ai.tool.name': 'Bash'}
        },
        {
            'trace_id': 't1',
            'span_id': 'c',
            'parent_span_id': 'b',
            'name': 'claude_code.tool.execution',
            'kind': 1,
            'start_time_unix_nano': 1700000000_600000000,
            'end_time_unix_nano': 1700000000_800000000,
            'resource_attrs': {'session_id': 's1'},
            'scope_name': 'claude-code',
            'span_attrs': {'gen_ai.operation.name': 'execute_tool'}
        },
    ]

    await spans_to_events_and_persist(spans, user_id='u1')

    db = get_db()
    cur = await db.execute('SELECT trace_id, span_id, parent_span_id, name, attributes FROM spans ORDER BY start_time')
    rows = [dict(r) for r in await cur.fetchall()]
    assert len(rows) == 3
    assert rows[0]['span_id'] == 'a'
    assert rows[1]['parent_span_id'] == 'a'
    assert rows[1]['name'] == 'claude_code.tool Bash'
    assert json.loads(rows[1]['attributes'])['span']['gen_ai.tool.name'] == 'Bash'

    cur2 = await db.execute("SELECT type, tool_name, duration_ms, error FROM events WHERE type LIKE 'tool%' ORDER BY timestamp, type")
    tool_events = [dict(r) for r in await cur2.fetchall()]
    # 2 tool spans. Each has start and end, so 2 events per span = 4 events.
    assert len(tool_events) == 4
    # Check that tool_call and tool_result were emitted
    assert [e['type'] for e in tool_events] == ['tool_call', 'tool_call', 'tool_result', 'tool_result']
    assert any(e['tool_name'] == 'Bash' for e in tool_events)

