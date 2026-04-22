#!/usr/bin/env python3
"""tracea-hook.py — Kimi CLI lifecycle hook for tracea observability.

Install: Add to ~/.kimi/config.toml:

    [[hooks]]
    event = "PreToolUse"
    command = "python3 /path/to/tracea-hook.py pre"

    [[hooks]]
    event = "PostToolUse"
    command = "python3 /path/to/tracea-hook.py post"

    [[hooks]]
    event = "PostToolUseFailure"
    command = "python3 /path/to/tracea-hook.py post_failure"

    [[hooks]]
    event = "SessionStart"
    command = "python3 /path/to/tracea-hook.py session_start"

    [[hooks]]
    event = "SessionEnd"
    command = "python3 /path/to/tracea-hook.py session_end"

Kimi CLI sends JSON context via stdin for every hook invocation.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import uuid
from datetime import datetime, timezone

SERVER_URL = os.environ.get("TRACEA_SERVER_URL", "http://localhost:8080")
API_KEY = os.environ.get("TRACEA_API_KEY", "dev-mode")
AGENT_ID = os.environ.get("TRACEA_AGENT_ID", "kimi")

# In-memory store to correlate pre/post tool calls within a process.
# Kimi runs PreToolUse and PostToolUse as separate subprocess calls,
# so we use a temp file keyed by session_id + tool_name.
_LAST_TCID_FILE = "/tmp/tracea-kimi-last-tcid"


def post_event(
    event_type: str,
    content: str | None = None,
    error: str | None = None,
    duration_ms: int = 0,
    tool_name: str | None = None,
    tool_call_id: str | None = None,
    session_id: str | None = None,
) -> int:
    """POST a single event to the tracea server. Returns HTTP status or 0 on failure."""
    sid = session_id or f"{AGENT_ID}-{os.getpid()}"
    tid = tool_call_id or str(uuid.uuid4())

    payload = {
        "events": [{
            "event_id": str(uuid.uuid4()),
            "session_id": sid,
            "agent_id": AGENT_ID,
            "sequence": 0,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "type": event_type,
            "provider": "kimi",
            "model": "",
            "content": content,
            "tool_call_id": tid,
            "tool_name": tool_name,
            "duration_ms": duration_ms,
            "error": error,
            "metadata": {
                "hook_type": event_type,
                "kimi_tool_name": tool_name,
            },
        }]
    }

    req = urllib.request.Request(
        f"{SERVER_URL}/api/v1/events/mcp",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read()
            if resp.status != 200:
                print(f"[tracea] ERROR: server returned HTTP {resp.status}", file=sys.stderr)
            return resp.status
    except Exception as exc:
        print(f"[tracea] ERROR: {exc}", file=sys.stderr)
        return 0


def _persist_tcid(tcid: str) -> None:
    try:
        with open(_LAST_TCID_FILE, "w") as f:
            f.write(tcid)
    except Exception:
        pass


def _read_tcid() -> str | None:
    try:
        with open(_LAST_TCID_FILE) as f:
            return f.read().strip()
    except Exception:
        return None


def _clear_tcid() -> None:
    try:
        os.remove(_LAST_TCID_FILE)
    except Exception:
        pass


def main() -> int:
    hook_type = sys.argv[1] if len(sys.argv) > 1 else ""

    # Read Kimi JSON context from stdin
    stdin_data = ""
    if not sys.stdin.isatty():
        try:
            stdin_data = sys.stdin.read()
        except Exception:
            pass

    ctx = {}
    if stdin_data:
        try:
            ctx = json.loads(stdin_data)
        except json.JSONDecodeError:
            pass

    session_id = ctx.get("session_id")
    tool_name = ctx.get("tool_name")
    tool_input = ctx.get("tool_input")
    tool_output = ctx.get("tool_output")
    tool_error = ctx.get("error")
    tcid = ctx.get("tool_call_id") or str(uuid.uuid4())

    if hook_type == "pre":
        content = json.dumps(tool_input) if tool_input else None
        _persist_tcid(tcid)
        post_event("tool_call", content=content, tool_name=tool_name,
                   tool_call_id=tcid, session_id=session_id)

    elif hook_type == "post":
        content = json.dumps(tool_output) if tool_output else None
        stored_tcid = _read_tcid() or tcid
        _clear_tcid()
        post_event("tool_result", content=content, tool_name=tool_name,
                   tool_call_id=stored_tcid, session_id=session_id)

    elif hook_type == "post_failure":
        content = json.dumps(tool_input) if tool_input else None
        stored_tcid = _read_tcid() or tcid
        _clear_tcid()
        post_event("tool_result", content=content, error=tool_error,
                   tool_name=tool_name, tool_call_id=stored_tcid,
                   session_id=session_id)

    elif hook_type == "session_start":
        post_event("session_start", session_id=session_id)

    elif hook_type == "session_end":
        post_event("session_end", session_id=session_id)
        _clear_tcid()

    else:
        print(f"Unknown hook type: {hook_type}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
