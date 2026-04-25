#!/usr/bin/env python3
"""tracea-hook.py — Gemini CLI lifecycle hook for tracea observability.

Install: Add to ~/.gemini/settings.json (or project .gemini/settings.json):

  {
    "hooks": {
      "BeforeTool": ["python3", "/path/to/tracea-hook.py", "before_tool"],
      "AfterTool": ["python3", "/path/to/tracea-hook.py", "after_tool"],
      "SessionStart": ["python3", "/path/to/tracea-hook.py", "session_start"],
      "SessionEnd": ["python3", "/path/to/tracea-hook.py", "session_end"]
    }
  }

Gemini CLI communicates with hooks via JSON over stdin/stdout.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import uuid
from datetime import datetime, timezone

SERVER_URL = os.environ.get("TRACEA_SERVER_URL", "http://localhost:8080")
AGENT_ID = os.environ.get("TRACEA_AGENT_ID", "gemini-cli")
USER_ID = os.environ.get("TRACEA_USER_ID", "")

_LAST_TCID_FILE = "/tmp/tracea-gemini-last-tcid"
_START_TIME_FILE = "/tmp/tracea-gemini-start-time"


def _persist_tcid(tcid: str, start_time: float | None = None) -> None:
    try:
        with open(_LAST_TCID_FILE, "w") as f:
            f.write(tcid)
        if start_time is not None:
            with open(_START_TIME_FILE, "w") as f:
                f.write(str(start_time))
    except Exception:
        pass


def _read_start_time() -> float | None:
    try:
        with open(_START_TIME_FILE) as f:
            return float(f.read().strip())
    except Exception:
        return None


def _clear_tcid() -> None:
    for f in (_LAST_TCID_FILE, _START_TIME_FILE):
        try:
            os.remove(f)
        except Exception:
            pass


def post_event(
    event_type: str,
    content: str | None = None,
    error: str | None = None,
    duration_ms: int = 0,
    tool_name: str | None = None,
    tool_call_id: str | None = None,
    session_id: str | None = None,
) -> None:
    """POST a single event to the tracea server."""
    sid = session_id or f"{AGENT_ID}-{os.getpid()}"
    tid = tool_call_id or str(uuid.uuid4())

    payload = {
        "events": [{
            "event_id": str(uuid.uuid4()),
            "session_id": sid,
            "agent_id": AGENT_ID,
            "user_id": USER_ID,
            "sequence": 0,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "type": event_type,
            "provider": "gemini-cli",
            "model": "",
            "content": content,
            "tool_call_id": tid,
            "tool_name": tool_name,
            "duration_ms": duration_ms,
            "error": error,
            "metadata": {
                "hook_type": event_type,
                "gemini_tool_name": tool_name,
            },
        }]
    }

    req = urllib.request.Request(
        f"{SERVER_URL}/api/v1/events/mcp",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read()
            if resp.status != 200:
                print(f"[tracea] ERROR: server returned HTTP {resp.status}", file=sys.stderr)
    except Exception as exc:
        print(f"[tracea] ERROR: {exc}", file=sys.stderr)


def main() -> None:
    hook_type = sys.argv[1] if len(sys.argv) > 1 else ""

    # Gemini CLI sends JSON payload on stdin for some hooks
    stdin_data = ""
    if not sys.stdin.isatty():
        try:
            stdin_data = sys.stdin.read()
        except Exception:
            pass

    payload = {}
    if stdin_data:
        try:
            payload = json.loads(stdin_data)
        except json.JSONDecodeError:
            pass

    session_id = payload.get("session_id") or os.environ.get("GEMINI_SESSION_ID")
    tool_name = payload.get("tool_name") or payload.get("name")
    tool_input = payload.get("tool_input") or payload.get("args")
    tool_output = payload.get("tool_output") or payload.get("result")
    tool_error = payload.get("error")
    tcid = payload.get("tool_call_id") or str(uuid.uuid4())

    if hook_type == "before_tool":
        content = json.dumps(tool_input) if tool_input else None
        _persist_tcid(tcid, start_time=datetime.now(timezone.utc).timestamp())
        post_event("tool_call", content=content, tool_name=tool_name,
                   tool_call_id=tcid, session_id=session_id)

    elif hook_type == "after_tool":
        content = json.dumps(tool_output) if tool_output else None
        error = tool_error
        start_time = _read_start_time()
        duration = payload.get("duration_ms", 0)
        if duration == 0 and start_time:
            duration = int((datetime.now(timezone.utc).timestamp() - start_time) * 1000)
        _clear_tcid()
        post_event("tool_result", content=content, error=error, duration_ms=duration,
                   tool_name=tool_name, tool_call_id=tcid,
                   session_id=session_id)

    elif hook_type == "session_start":
        post_event("session_start", session_id=session_id)

    elif hook_type == "session_end":
        post_event("session_end", session_id=session_id)

    else:
        print(f"Unknown hook type: {hook_type}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
