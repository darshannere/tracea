"""Session context management via contextvars.

tracea.session() context manager and explicit session_id support.
Session ID is environment-derived (hostname + pid) for context manager path.
Explicit session_id param passed directly through.
"""
from __future__ import annotations
import os
import uuid
from contextvars import ContextVar
from typing import Any
from contextlib import asynccontextmanager

# Session context: session_id, metadata dict, tags list, agent_id
# Use None as sentinel default to avoid mutable default dict corruption
_session_ctx: ContextVar[dict[str, Any] | None] = ContextVar("session", default=None)

def derive_session_id() -> str:
    """Derive a deterministic session ID from hostname + process ID.

    Used for the context manager path where user does not provide explicit session_id.
    """
    host = os.uname().nodename if hasattr(os, "uname") else "unknown"
    pid = os.getpid()
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{host}-{pid}"))

def get_session_ctx() -> dict[str, Any]:
    """Return the current session context dict.

    Returns empty dict if no session is active. Safe default —
    patched send() always has a session_id available.
    """
    ctx = _session_ctx.get()
    return ctx if ctx is not None else {}

@asynccontextmanager
async def session(
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
    emit_events: bool = True,
):
    """Async context manager for session-scoped tracea instrumentation.

    Usage:
        async with tracea.session(metadata={"user_id": "123"}):
            # All LLM calls within this block are associated with this session
            response = client.chat.completions.create(...)

    If session_id is not provided, it is derived from hostname + process ID.

    Args:
        metadata: Session-level metadata applied to all events.
        tags: Session-level tags applied to all events.
        agent_id: Agent identifier (e.g. "my-bot-v2").
        session_id: Explicit session ID. If omitted, derived deterministically.
        emit_events: If True (default), emits ``session_start`` on enter and
                     ``session_end`` on exit.
    """
    resolved_session_id = session_id or derive_session_id()

    # Merge metadata: init-level metadata is applied at init time
    # session-level can extend/override
    merged_metadata = metadata or {}

    ctx = {
        "session_id": resolved_session_id,
        "metadata": merged_metadata,
        "tags": tags or [],
        "agent_id": agent_id or "",
    }

    token = _session_ctx.set(ctx)

    # Emit session_start before yielding
    if emit_events:
        try:
            from tracea.log import log_event
            log_event(
                event_type="session_start",
                metadata={"tags": tags or [], **merged_metadata},
            )
        except Exception:
            pass  # Never fail session setup

    try:
        yield ctx
    finally:
        # Emit session_end before resetting context
        if emit_events:
            try:
                from tracea.log import log_event
                log_event(
                    event_type="session_end",
                    metadata={"tags": tags or [], **merged_metadata},
                )
            except Exception:
                pass  # Never fail session teardown

        _session_ctx.reset(token)
