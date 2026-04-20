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
_session_ctx: ContextVar[dict[str, Any]] = ContextVar("session", default={})

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
    return _session_ctx.get()

@asynccontextmanager
async def session(
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
):
    """Async context manager for session-scoped tracea instrumentation.

    Usage:
        async with tracea.session(metadata={"user_id": "123"}):
            # All LLM calls within this block are associated with this session
            response = client.chat.completions.create(...)

    If session_id is not provided, it is derived from hostname + process ID.
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
    try:
        yield ctx
    finally:
        _session_ctx.reset(token)
