"""High-level logging functions for direct event emission.

These helpers let users log tool calls, chat messages, errors, and custom events
directly — without relying on the httpx transport interception. They are
fire-and-forget: they never block the caller and never raise exceptions.

Usage:
    import tracea
    tracea.init(api_key="dev-mode")

    tracea.log_tool_call("search", {"query": "python"})
    tracea.log_tool_result("search", result={"hits": [...]}, duration_ms=120)

    tracea.log_chat(role="user", content="Hello", model="gpt-4o")
    tracea.log_error("Something went wrong")
"""
from __future__ import annotations
import asyncio
import threading
import time
from typing import Any
from uuid import uuid4
from datetime import datetime, timezone

from tracea.events import TracedEvent, TokenUsage
from tracea.session import get_session_ctx, derive_session_id


def _resolve_session_id() -> str:
    """Return the active session ID or derive a deterministic one."""
    ctx = get_session_ctx()
    return ctx.get("session_id") or str(derive_session_id())


def _resolve_agent_id() -> str:
    """Return the active agent_id or empty string."""
    ctx = get_session_ctx()
    return ctx.get("agent_id") or ""


def _resolve_metadata(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge session-level metadata with any per-event metadata."""
    ctx = get_session_ctx()
    merged: dict[str, Any] = dict(ctx.get("metadata", {}))
    if extra:
        merged.update(extra)
    return merged


def _build_event(
    event_type: str,
    content: str | None = None,
    tool_name: str | None = None,
    tool_call_id: str | None = None,
    error: str | None = None,
    duration_ms: int = 0,
    model: str = "",
    role: str | None = None,
    provider: str = "unknown",
    tokens_used: TokenUsage | None = None,
    cost_usd: float | None = None,
    metadata: dict[str, Any] | None = None,
    **extra_fields: Any,
) -> TracedEvent:
    """Build a TracedEvent with sensible defaults."""
    ctx = get_session_ctx()
    return TracedEvent(
        event_id=uuid4(),
        session_id=uuid5_session_id(_resolve_session_id()),
        agent_id=_resolve_agent_id(),
        sequence=0,  # sequence is managed by buffer if needed
        timestamp=datetime.now(timezone.utc),
        type=event_type,  # type: ignore[arg-type]
        provider=provider,  # type: ignore[arg-type]
        model=model,
        role=role,  # type: ignore[arg-type]
        content=content,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        error=error,
        duration_ms=duration_ms,
        tokens_used=tokens_used,
        cost_usd=cost_usd,
        metadata=_resolve_metadata(metadata),
        **extra_fields,
    )


def uuid5_session_id(session_id: str) -> Any:
    """Convert string session_id to UUID (stable mapping via uuid5)."""
    from uuid import UUID, uuid5
    try:
        return UUID(session_id)
    except ValueError:
        return uuid5(UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8"), session_id)


def _emit_fire_and_forget(event: TracedEvent) -> None:
    """Add event to buffer without blocking or raising.

    If an async loop is running, schedules buffer.add() as a background task.
    If no loop is running, runs it in a daemon thread with its own loop.
    """
    try:
        from tracea.buffer import get_buffer

        buffer = get_buffer()
    except Exception:
        # Buffer not ready — silently drop
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        # Inside async context — schedule without awaiting
        try:
            loop.create_task(buffer.add(event))
        except Exception:
            pass
    else:
        # No running loop — fire in a daemon thread
        def _post() -> None:
            try:
                asyncio.run(buffer.add(event))
            except Exception:
                pass

        try:
            threading.Thread(target=_post, daemon=True).start()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def log_tool_call(
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    tool_call_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Log the start of a tool call (fire-and-forget).

    Args:
        tool_name: Name of the tool being invoked.
        arguments: Arguments passed to the tool (serialized to JSON in content).
        tool_call_id: Optional ID correlating with a later result.
        metadata: Additional metadata for this event.
    """
    import json

    content = json.dumps(arguments) if arguments else None
    event = _build_event(
        event_type="tool_call",
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        content=content,
        metadata=metadata,
    )
    _emit_fire_and_forget(event)


def log_tool_result(
    tool_name: str,
    result: Any = None,
    error: str | None = None,
    duration_ms: int = 0,
    tool_call_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Log the result (or error) of a tool call (fire-and-forget).

    Args:
        tool_name: Name of the tool that was invoked.
        result: The result value (serialized to JSON in content).
        error: Error message if the tool failed.
        duration_ms: Duration of the tool execution in milliseconds.
        tool_call_id: Optional ID correlating with the call event.
        metadata: Additional metadata for this event.
    """
    import json

    content = json.dumps(result) if result is not None else None
    event = _build_event(
        event_type="tool_result",
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        content=content,
        error=error,
        duration_ms=duration_ms,
        metadata=metadata,
    )
    _emit_fire_and_forget(event)


def log_chat(
    role: str,
    content: str,
    model: str = "",
    provider: str = "unknown",
    metadata: dict[str, Any] | None = None,
) -> None:
    """Log a chat message outside of httpx interception (fire-and-forget).

    Useful when the LLM call is not going through httpx (e.g. local model,
    custom transport, or streaming not captured by the patch).

    Args:
        role: "user", "assistant", or "system".
        content: Message content.
        model: Model name (e.g. "gpt-4o", "claude-3-5-sonnet").
        provider: Provider slug (e.g. "openai", "anthropic", "ollama").
        metadata: Additional metadata.
    """
    event = _build_event(
        event_type="chat.completion",
        role=role,  # type: ignore[arg-type]
        content=content,
        model=model,
        provider=provider,  # type: ignore[arg-type]
        metadata=metadata,
    )
    _emit_fire_and_forget(event)


def log_error(
    error: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Log an error event (fire-and-forget).

    Args:
        error: Error message or description.
        metadata: Additional metadata.
    """
    event = _build_event(
        event_type="error",
        error=error,
        metadata=metadata,
    )
    _emit_fire_and_forget(event)


def log_event(
    event_type: str,
    content: str | None = None,
    metadata: dict[str, Any] | None = None,
    **kwargs: Any,
) -> None:
    """Log a fully custom event (fire-and-forget).

    Args:
        event_type: Any event type string (also sent to the server).
        content: Optional content payload.
        metadata: Additional metadata.
        **kwargs: Any additional TracedEvent fields (model, role, etc.).
    """
    event = _build_event(
        event_type=event_type,
        content=content,
        metadata=metadata,
        **kwargs,
    )
    _emit_fire_and_forget(event)


# ---------------------------------------------------------------------------
# Context-manager friendly helpers with automatic timing
# ---------------------------------------------------------------------------

class LogTool:
    """Context manager for timing a tool call and auto-logging start + result.

    Usage:
        with tracea.LogTool("search") as lt:
            result = do_search(query="python")
            lt.result = result

    This emits a tool_call event on enter and a tool_result event on exit
    with the elapsed duration.
    """

    def __init__(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        tool_call_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.tool_name = tool_name
        self.arguments = arguments
        self.tool_call_id = tool_call_id or str(uuid4())
        self.metadata = metadata
        self.result: Any = None
        self.error: str | None = None
        self._start: float = 0.0

    def __enter__(self) -> "LogTool":
        self._start = time.monotonic()
        log_tool_call(
            tool_name=self.tool_name,
            arguments=self.arguments,
            tool_call_id=self.tool_call_id,
            metadata=self.metadata,
        )
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        duration_ms = int((time.monotonic() - self._start) * 1000)
        if exc_val is not None:
            self.error = str(exc_val)
        log_tool_result(
            tool_name=self.tool_name,
            result=self.result,
            error=self.error,
            duration_ms=duration_ms,
            tool_call_id=self.tool_call_id,
            metadata=self.metadata,
        )
