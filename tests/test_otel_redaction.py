import os
import pytest
from tracea.server.otel.mapper import logs_to_events

def test_redaction_off_by_default(monkeypatch):
    monkeypatch.setenv("TRACEA_CAPTURE_CONTENT", "1")
    monkeypatch.delenv("TRACEA_REDACT_CONTENT", raising=False)
    log = {
        "scope_name": "claude-code",
        "timestamp_unix_nano": 0,
        "body": "my key is sk-abcd1234efgh5678ijkl9012mnop3456",
        "resource_attrs": {"session_id": "s"},
        "log_attrs": {"event.name": "claude_code.user_prompt"},
    }
    e = logs_to_events([log])[0]
    assert "sk-abcd1234" in e.content


def test_redaction_on_scrubs_secrets(monkeypatch):
    monkeypatch.setenv("TRACEA_CAPTURE_CONTENT", "1")
    monkeypatch.setenv("TRACEA_REDACT_CONTENT", "1")
    log = {
        "scope_name": "claude-code",
        "timestamp_unix_nano": 0,
        "body": "my key is sk-abcd1234efgh5678ijkl9012mnop3456",
        "resource_attrs": {"session_id": "s"},
        "log_attrs": {"event.name": "claude_code.user_prompt"},
    }
    e = logs_to_events([log])[0]
    assert "sk-abcd1234" not in e.content
    assert "REDACTED" in e.content


def test_genai_messages_redaction(monkeypatch):
    monkeypatch.setenv("TRACEA_CAPTURE_CONTENT", "1")
    monkeypatch.setenv("TRACEA_REDACT_CONTENT", "1")
    log = {
        "scope_name": "genai",
        "timestamp_unix_nano": 0,
        "body": "",
        "resource_attrs": {"gen_ai.system": "gemini"},
        "log_attrs": {
            "event.name": "gen_ai.client.inference.operation.details",
            "gen_ai.request.model": "gemini-2.5-pro",
            "gen_ai.input.messages": [
                {
                    "role": "user",
                    "parts": [{"type": "text", "text": "token=ghp_abcdefghijklmnopqrstuvwxyz0123456789"}],
                }
            ],
            "gen_ai.output.messages": [],
        },
    }
    events = logs_to_events([log])
    user_evt = [x for x in events if x.role == "user"][0]
    assert "ghp_" not in user_evt.content
    assert "REDACTED" in user_evt.content
