from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from tracea.server.models import TracedEvent, TokenUsage


# ---------------------------------------------------------------------------
# Public entry point (called by otlp.py route)
# ---------------------------------------------------------------------------

def logs_to_events(logs: list[dict], user_id: str = "") -> list[TracedEvent]:
    """Map OTLP log records → TracedEvent list.

    Dispatches by source (Claude Code vs generic GenAI). GenAI dispatch is
    added in Task 5.
    """
    events: list[TracedEvent] = []
    capture_content = os.environ.get("TRACEA_CAPTURE_CONTENT", "1") != "0"

    for log in logs:
        try:
            if not isinstance(log, dict):
                raise TypeError("Log record must be a dict")
            if _is_claude_code(log):
                events.extend(_claude_code_log_to_events(log, user_id, capture_content))
            # Task 5 adds: elif _is_genai_inference(log): events.extend(_genai_log_to_events(...))
        except Exception as exc:
            # Never let one bad log drop the whole batch
            events.append(_error_event(log, str(exc), user_id))
    return events


# ---------------------------------------------------------------------------
# Claude Code detection + mapping
# ---------------------------------------------------------------------------

def _is_claude_code(log: Any) -> bool:
    if not isinstance(log, dict):
        return False
    if log.get("scope_name") == "claude-code":
        return True
    attrs = log.get("log_attrs", {}) or {}
    event_name = attrs.get("event.name", "")
    if isinstance(event_name, str) and event_name.startswith("claude_code."):
        return True
    return False


def _claude_code_log_to_events(
    log: dict, user_id: str, capture_content: bool
) -> list[TracedEvent]:
    attrs = log.get("log_attrs", {}) or {}
    resource_attrs = log.get("resource_attrs", {}) or {}
    event_name = attrs.get("event.name", "")
    body = log.get("body")
    ts = _ns_to_datetime(log.get("timestamp_unix_nano", 0))

    session_id = _derive_session_id(log)
    agent_id = str(resource_attrs.get("agent_id") or "claude-code")

    common = dict(
        session_id=session_id,
        agent_id=agent_id,
        user_id=user_id,
        timestamp=ts,
        provider="claude-code",
        metadata={
            "integration": "otlp",
            "source": "claude-code",
            "event.name": event_name,
            "trace_id": log.get("trace_id"),
            "span_id": log.get("span_id"),
        },
    )

    if event_name == "claude_code.user_prompt":
        content = body if isinstance(body, str) else _stringify(body)
        return [TracedEvent(
            event_id=str(uuid4()),
            type="chat.completion", role="user",
            content=content if capture_content else None,
            **common,
        )]

    if event_name == "claude_code.assistant_response":
        content = body if isinstance(body, str) else _stringify(body)
        return [TracedEvent(
            event_id=str(uuid4()),
            type="chat.completion", role="assistant",
            content=content if capture_content else None,
            **common,
        )]

    if event_name == "claude_code.api_request_body":
        return [_from_anthropic_request(body, capture_content, common)]

    if event_name == "claude_code.api_response_body":
        return [_from_anthropic_response(body, capture_content, common)]

    if event_name == "claude_code.tool_result":
        return [TracedEvent(
            event_id=str(uuid4()),
            type="tool_result",
            tool_name=attrs.get("tool_name") or attrs.get("gen_ai.tool.name"),
            content=(_stringify(body) if capture_content else None),
            **common,
        )]

    if event_name in ("claude_code.api_error", "claude_code.api_refusal"):
        return [TracedEvent(
            event_id=str(uuid4()),
            type="error",
            error=(body if isinstance(body, str) else _stringify(body)) or event_name,
            **common,
        )]

    # api_request and anything else → metadata-only marker
    return [TracedEvent(
        event_id=str(uuid4()),
        type="chat.completion",
        content=None,
        **common,
    )]


def _from_anthropic_request(
    body: Any, capture_content: bool, common: dict
) -> TracedEvent:
    """Parse a claude_code.api_request_body JSON string."""
    data = _parse_json_body(body)
    model = data.get("model", "") if isinstance(data, dict) else ""
    messages = data.get("messages", []) if isinstance(data, dict) else []

    # Find the LAST user message
    last_user_text = ""
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            last_user_text = _flatten_message_content(msg.get("content"))
            break

    meta = dict(common["metadata"])
    meta["request_model"] = model
    if capture_content and data:
        meta["raw_body"] = data  # full request JSON for RCA / forensics

    return TracedEvent(
        event_id=str(uuid4()),
        type="chat.completion",
        role="user",
        content=last_user_text if capture_content else None,
        model=model,
        **{**common, "metadata": meta},
    )


def _from_anthropic_response(
    body: Any, capture_content: bool, common: dict
) -> TracedEvent:
    """Parse a claude_code.api_response_body JSON string."""
    data = _parse_json_body(body)
    if not isinstance(data, dict):
        return TracedEvent(
            event_id=str(uuid4()),
            type="chat.completion", role="assistant",
            content=None, **common,
        )

    model = data.get("model", "")
    content_blocks = data.get("content", [])
    text_parts = [
        b.get("text", "")
        for b in content_blocks
        if isinstance(b, dict) and b.get("type") == "text"
    ]
    assistant_text = "\n".join(p for p in text_parts if p)

    usage_raw = data.get("usage", {}) or {}
    tokens = None
    if usage_raw:
        tokens = TokenUsage(
            input=int(usage_raw.get("input_tokens", 0) or 0),
            output=int(usage_raw.get("output_tokens", 0) or 0),
            total=int(usage_raw.get("input_tokens", 0) or 0)
                 + int(usage_raw.get("output_tokens", 0) or 0),
        )
    cost = _estimate_cost(tokens)

    meta = dict(common["metadata"])
    meta["response_id"] = data.get("id")
    meta["stop_reason"] = data.get("stop_reason")
    if capture_content:
        meta["raw_body"] = data

    return TracedEvent(
        event_id=str(uuid4()),
        type="chat.completion",
        role="assistant",
        content=assistant_text if capture_content else None,
        model=model,
        tokens_used=tokens,
        cost_usd=cost,
        **{**common, "metadata": meta},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _derive_session_id(log: Any) -> str:
    if isinstance(log, dict):
        resource_attrs = log.get("resource_attrs", {}) or {}
        for key in ("session_id", "claude_code.session_id"):
            val = resource_attrs.get(key)
            if val:
                return str(val)
        # Fallback to trace_id (a span/log without a session is still groupable
        # by its trace)
        if log.get("trace_id"):
            return f"trace-{log['trace_id']}"
    return f"unknown-{uuid4()}"


def _parse_json_body(body: Any) -> Any:
    if isinstance(body, str):
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {}
    return body if body is not None else {}


def _flatten_message_content(content: Any) -> str:
    """Anthropic message content: either a string or a list of blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif "text" in block:
                    parts.append(str(block["text"]))
        return "\n".join(p for p in parts if p)
    return _stringify(content)


def _stringify(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    try:
        return json.dumps(x)
    except Exception:
        return str(x)


def _ns_to_datetime(ns: int) -> datetime:
    if not ns:
        return datetime.now(timezone.utc)
    return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc)


def _estimate_cost(tokens: TokenUsage | None) -> float | None:
    if tokens and tokens.total > 0:
        return round(tokens.total * 0.00001, 6)
    return None


def _error_event(log: Any, msg: str, user_id: str) -> TracedEvent:
    log_attrs = log.get("log_attrs") if isinstance(log, dict) else None
    event_name = (log_attrs or {}).get("event.name") if isinstance(log_attrs, dict) else None
    scope_name = log.get("scope_name") if isinstance(log, dict) else None

    return TracedEvent(
        event_id=str(uuid4()),
        session_id=_derive_session_id(log),
        agent_id=str(scope_name or "otlp"),
        user_id=user_id,
        timestamp=datetime.now(timezone.utc),
        type="error",
        provider="unknown",
        error=f"OTLP log mapping failed: {msg}",
        metadata={"integration": "otlp", "event.name": event_name},
    )


# ---------------------------------------------------------------------------
# Stubs (Tasks 6, 7)
# ---------------------------------------------------------------------------

async def spans_to_events_and_persist(spans: list[dict], user_id: str) -> None:
    """Implemented in Task 6."""
    return None


async def persist_metrics(metrics: list[dict], user_id: str) -> None:
    """Implemented in Task 7."""
    return None

