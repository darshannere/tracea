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
    """Map OTLP log records to tracea TracedEvents.

    Called by the /v1/logs route. Normalizes Claude Code and Gemini log events
    to tracea event schema.
    """
    events: list[TracedEvent] = []
    capture_content = os.environ.get("TRACEA_CAPTURE_CONTENT", "1") != "0"
    redact_content = os.environ.get("TRACEA_REDACT_CONTENT", "0") == "1"

    for log in logs:
        try:
            if not isinstance(log, dict):
                raise TypeError("Log record must be a dict")
            if redact_content:
                log = _redact_log(log)
            if _is_claude_code(log):
                events.extend(_claude_code_log_to_events(log, user_id, capture_content))
            elif _is_genai_inference(log):
                events.extend(_genai_log_to_events(log, user_id, capture_content))
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
    cost = _estimate_cost(tokens, "anthropic", model)

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
# Generic GenAI inference event (Gemini CLI + spec-compliant clients)
# ---------------------------------------------------------------------------

_GENAI_INFERENCE_EVENT = "gen_ai.client.inference.operation.details"


def _is_genai_inference(log: dict) -> bool:
    attrs = log.get("log_attrs", {}) or {}
    return attrs.get("event.name") == _GENAI_INFERENCE_EVENT


def _genai_log_to_events(
    log: dict, user_id: str, capture_content: bool
) -> list[TracedEvent]:
    attrs = log.get("log_attrs", {}) or {}
    resource_attrs = log.get("resource_attrs", {}) or {}
    ts = _ns_to_datetime(log.get("timestamp_unix_nano", 0))

    model = attrs.get("gen_ai.response.model") or attrs.get("gen_ai.request.model") or ""
    provider = _genai_provider(resource_attrs, attrs)
    session_id = _derive_genai_session_id(log, resource_attrs)

    # Token usage
    in_tok = _to_int(attrs.get("gen_ai.usage.input_tokens"))
    out_tok = _to_int(attrs.get("gen_ai.usage.output_tokens"))
    tokens = None
    if in_tok or out_tok:
        tokens = TokenUsage(input=in_tok, output=out_tok, total=in_tok + out_tok)
    cost = _estimate_cost(tokens, provider, model)

    common_no_tokens = dict(
        session_id=session_id,
        agent_id=str(resource_attrs.get("agent_id") or provider),
        user_id=user_id,
        timestamp=ts,
        provider=provider,
        model=model,
        metadata={
            "integration": "otlp",
            "source": provider,
            "event.name": _GENAI_INFERENCE_EVENT,
            "response_id": attrs.get("gen_ai.response.id"),
            "trace_id": log.get("trace_id"),
            "span_id": log.get("span_id"),
        },
    )

    events: list[TracedEvent] = []

    # System instructions → role=system
    sys_instr = attrs.get("gen_ai.system_instructions")
    if capture_content and sys_instr:
        events.append(TracedEvent(
            event_id=str(uuid4()),
            type="chat.completion", role="system",
            content=_stringify(sys_instr),
            **common_no_tokens,
        ))

    # Input messages → one chat.completion per message with its role
    for msg in attrs.get("gen_ai.input.messages", []) or []:
        if not isinstance(msg, dict):
            continue
        events.append(TracedEvent(
            event_id=str(uuid4()),
            type="chat.completion",
            role=_normalize_role(msg.get("role", "user")),
            content=_flatten_genai_parts(msg.get("parts", [])) if capture_content else None,
            **common_no_tokens,
        ))

    # Output messages → role=assistant. Attach tokens/cost ONLY to the last
    # output event so session aggregates don't multi-count (one inference =
    # one billable token batch).
    output_msgs = [m for m in (attrs.get("gen_ai.output.messages") or []) if isinstance(m, dict)]
    for idx, msg in enumerate(output_msgs):
        is_last = (idx == len(output_msgs) - 1)
        events.append(TracedEvent(
            event_id=str(uuid4()),
            type="chat.completion",
            role="assistant",
            content=_flatten_genai_parts(msg.get("parts", [])) if capture_content else None,
            tokens_used=tokens if is_last else None,
            cost_usd=cost if is_last else None,
            **common_no_tokens,
        ))

    # If we produced nothing structured, emit a metadata-only marker so the
    # session still shows up in the dashboard.
    if not events:
        events.append(TracedEvent(
            event_id=str(uuid4()),
            type="chat.completion",
            content=None,
            tokens_used=tokens,
            cost_usd=cost,
            **common_no_tokens,
        ))

    return events


def _flatten_genai_parts(parts: list) -> str:
    """Concatenate text parts. Tool-call parts are skipped (handled via spans in Task 6)."""
    if not parts:
        return ""
    out = []
    for part in parts:
        if not isinstance(part, dict):
            out.append(_stringify(part))
            continue
        ptype = part.get("type")
        if ptype == "text" or "text" in part:
            out.append(str(part.get("text", "")))
        # tool_call / tool_call_response parts → ignored here; Task 6 emits
        # separate tool_call/tool_result events from the spans signal.
    return "\n".join(s for s in out if s)


def _normalize_role(role: str) -> str:
    r = (role or "user").lower()
    if r in ("user", "assistant", "system"):
        return r
    # Common alternates: "model" (Gemini), "bot", "machine"
    if r in ("model", "bot"):
        return "assistant"
    return "user"


def _to_int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _genai_provider(resource_attrs: dict, log_attrs: dict) -> str:
    """Resolve the tracea provider string. Maps OTel gen_ai.system values."""
    sys_val = (resource_attrs.get("gen_ai.system")
               or log_attrs.get("gen_ai.system")
               or "")
    sys_val = str(sys_val).lower()
    mapping = {
        "gemini": "gemini-cli",
        "google": "gemini-cli",
        "anthropic": "claude-code",
        "openai": "openai",
        "azure_openai": "azure_openai",
        "ollama": "ollama",
    }
    # TracedEvent.provider is a closed Literal — unknown gen_ai.system values
    # MUST fall back to "unknown" or pydantic raises and the whole log becomes
    # an error event.
    return mapping.get(sys_val, "unknown")


def _derive_genai_session_id(log: dict, resource_attrs: dict) -> str:
    """Gemini CLI sets session.id and process.id in resource attributes."""
    for key in ("session.id", "session_id", "process.id", "tracea.session_id"):
        val = resource_attrs.get(key)
        if val:
            return str(val)
    if log.get("trace_id"):
        return f"trace-{log['trace_id']}"
    return f"unknown-{uuid4()}"


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


def _estimate_cost(tokens: TokenUsage | None, provider: str = "", model: str = "") -> float | None:
    if not tokens or tokens.total == 0:
        return None
    from tracea.server.pricing import estimate_cost
    precise = estimate_cost(provider, model, tokens.input, tokens.output)
    if precise is not None:
        return precise
    # Fallback: old rough heuristic for unknown providers
    return round(tokens.total * 0.00001, 6)


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

async def spans_to_events_and_persist(spans: list[dict], user_id: str = "") -> None:
    """Persist all spans, then emit tool events for tool-execution spans.

    Called by the /v1/traces route. Persists every span to the spans table
    (for tree visualization) and extracts tool_call/tool_result events from
    gen_ai.execute_tool spans so they appear in the session event stream.
    """
    if not spans:
        return

    from tracea.server.db import enqueue_spans, enqueue_events, flush_events

    # 1. Persist every span
    await enqueue_spans(spans)

    # 2. Build parent_id → tool_name map so nested tool spans can inherit the tool name from their parent.
    parent_tool_names: dict[str, str] = {}
    for s in spans:
        attrs = s.get("span_attrs", {}) or {}
        tn = (
            attrs.get("gen_ai.tool.name")
            or attrs.get("tool_name")
            or _tool_name_from_span_name(s.get("name") or "")
        )
        if tn and s.get("span_id"):
            parent_tool_names[s["span_id"]] = tn

    # 3. Extract tool events
    tool_events: list[TracedEvent] = []
    for span in spans:
        events = _span_to_tool_events(span, user_id, parent_tool_names)
        tool_events.extend(events)

    if tool_events:
        await enqueue_events(tool_events)
        await flush_events()
        import asyncio
        from tracea.server.detection.engine import run_detection
        asyncio.create_task(run_detection(tool_events))


def _span_to_tool_events(
    span: dict, user_id: str, parent_tool_names: dict | None = None
) -> list[TracedEvent]:
    """Emit tool_call (and tool_result if the span finished) for tool spans.

    If the span's own attributes don't carry a tool name, inherit from the parent span.
    """
    attrs = span.get("span_attrs", {}) or {}
    resource_attrs = span.get("resource_attrs", {}) or {}
    parent_tool_names = parent_tool_names or {}

    is_tool = (
        attrs.get("gen_ai.operation.name") == "execute_tool"
        or "gen_ai.tool.call.id" in attrs
        or (span.get("name") or "").startswith("tool")
        or (span.get("name") or "").endswith(".tool.execution")
    )
    if not is_tool:
        return []

    tool_call_id = str(attrs.get("gen_ai.tool.call.id") or span.get("span_id") or uuid4())
    parent_id = span.get("parent_span_id") or ""
    tool_name = (
        attrs.get("gen_ai.tool.name")
        or attrs.get("tool_name")
        or parent_tool_names.get(parent_id, "")
        or _tool_name_from_span_name(span.get("name") or "")
        or "unknown"
    )
    session_id = _span_session_id_local(span, resource_attrs)
    provider = _genai_provider(resource_attrs, attrs)
    ts = _ns_to_datetime(span.get("start_time_unix_nano", 0))

    common = dict(
        session_id=session_id,
        agent_id=str(resource_attrs.get("agent_id") or provider),
        user_id=user_id,
        timestamp=ts,
        provider=provider,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        metadata={
            "integration": "otlp",
            "source": "span",
            "trace_id": span.get("trace_id"),
            "span_id": span.get("span_id"),
            "parent_span_id": span.get("parent_span_id"),
        },
    )

    events: list[TracedEvent] = [TracedEvent(
        event_id=str(uuid4()),
        type="tool_call",
        **common,
    )]

    # If the span has an end_time, it finished → emit tool_result
    if span.get("end_time_unix_nano"):
        end_ts = _ns_to_datetime(span["end_time_unix_nano"])
        duration_ms = int((span["end_time_unix_nano"] - span.get("start_time_unix_nano", 0)) / 1e6)
        events.append(TracedEvent(
            event_id=str(uuid4()),
            type="tool_result",
            timestamp=end_ts,
            duration_ms=max(duration_ms, 0),
            error=attrs.get("error.message") or attrs.get("exception.message"),
            **{k: v for k, v in common.items() if k != "timestamp"},
        ))

    return events


def _tool_name_from_span_name(name: str) -> str:
    """Extract tool name from a span like 'tool Bash' or 'claude_code.tool.execution'."""
    if not name:
        return ""
    parts = name.split()
    if len(parts) >= 2:
        return parts[1]
    if "." in name:
        return name.split(".")[-2] if name.count(".") >= 2 else ""
    return name


def _span_session_id_local(span: dict, resource_attrs: dict) -> str:
    for key in ("session_id", "claude_code.session_id", "session.id", "process.id"):
        val = resource_attrs.get(key)
        if val:
            return str(val)
    if span.get("trace_id"):
        return f"trace-{span['trace_id']}"
    return f"unknown-{uuid4()}"


async def persist_metrics(metrics: list[dict], user_id: str = "") -> None:
    """Persist OTel metric data points to the metrics table.

    v1 stores raw data points only — no aggregation, no mapping to events.
    The dashboard reads the metrics table directly in v2.
    """
    if not metrics:
        return
    from tracea.server.db import enqueue_metrics
    await enqueue_metrics(metrics)

    # Fire metric-based detection rules for any sessions touched
    import asyncio
    from tracea.server.detection.engine import run_metric_detection
    session_ids = {m.get("resource_attrs", {}).get("session_id")
                   or m.get("resource_attrs", {}).get("session.id")
                   for m in metrics}
    session_ids.discard(None)
    for sid in session_ids:
        asyncio.create_task(run_metric_detection(sid))


def _redact_log(log: dict) -> dict:
    """Return a copy of the log with secrets scrubbed from body and attrs.

    Uses tracea.server.redaction. Operates on:
    - log['body'] (string or JSON-string)
    - log['log_attrs'] values that look like content (event.name in
      {claude_code.user_prompt, claude_code.assistant_response,
       claude_code.api_request_body, claude_code.api_response_body})
    """
    from tracea.server.redaction import redact, redact_dict

    log = dict(log)  # shallow copy
    body = log.get("body")
    if isinstance(body, str):
        log["body"] = redact(body)
    elif isinstance(body, dict):
        log["body"] = redact_dict(body)

    attrs = log.get("log_attrs")
    if isinstance(attrs, dict):
        # Redact known content-carrying attributes
        CONTENT_KEYS = {
            "gen_ai.system_instructions",
            "gen_ai.input.messages",
            "gen_ai.output.messages",
        }
        redacted_attrs = dict(attrs)
        for k in CONTENT_KEYS:
            if k in redacted_attrs:
                redacted_attrs[k] = _redact_genai_messages(redacted_attrs[k])
        log["log_attrs"] = redacted_attrs
    return log


def _redact_genai_messages(value):
    """Recursively redact text within gen_ai.*.messages structures."""
    from tracea.server.redaction import redact
    if isinstance(value, list):
        return [_redact_genai_messages(v) for v in value]
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k == "text" and isinstance(v, str):
                out[k] = redact(v)
            else:
                out[k] = _redact_genai_messages(v)
        return out
    if isinstance(value, str):
        return redact(value)
    return value

