"""Session tracking for tracea-mcp."""
import os
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class MCPSession:
    """Tracks session state for one MCP server invocation."""

    session_id: str
    agent_id: str
    started_at: str
    sequence: int = 0
    ended: bool = False

    def next_sequence(self) -> int:
        self.sequence += 1
        return self.sequence

    def end(self):
        self.ended = True


_sequences: dict[str, int] = {}


def create_session(agent_id: str = "claude-code") -> MCPSession:
    """Create a new session for this MCP server invocation."""
    host = os.uname().nodename if hasattr(os, "uname") else "unknown"
    pid = os.getpid()
    start_time = int(time.time())
    session_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{host}-{pid}-{start_time}"))
    return MCPSession(
        session_id=session_id,
        agent_id=agent_id,
        started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )


def next_sequence_for(session_id: str) -> int:
    """Increment and return next sequence number for session."""
    if session_id not in _sequences:
        _sequences[session_id] = 0
    _sequences[session_id] += 1
    return _sequences[session_id]
