"""Event building for tracea-mcp tool call events."""
import json
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Any, Optional


@dataclass
class TokenUsage:
    input: int = 0
    output: int = 0
    total: int = 0


@dataclass
class TracedEvent:
    """Event dataclass matching tracea server schema."""

    event_id: str
    session_id: str
    agent_id: str
    user_id: str = ""
    sequence: int = 0
    timestamp: str = ""
    type: str = ""  # "tool_call", "tool_result", "error"
    provider: str = ""  # "claude-code" or "openclaw"
    model: str = ""
    tool_name: Optional[str] = None
    content: Optional[str] = None
    status_code: Optional[int] = None
    error: Optional[str] = None
    duration_ms: int = 0
    tokens_used: Optional[TokenUsage] = None
    cost_usd: Optional[float] = None
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.tokens_used:
            d["tokens_used"] = asdict(self.tokens_used)
        else:
            d["tokens_used"] = None
        return d


def build_tool_call_event(
    session_id: str,
    agent_id: str,
    sequence: int,
    tool_name: str,
    tool_input: dict,
    duration_ms: int = 0,
    user_id: str = "",
    integration: str = "tracea-mcp",
) -> TracedEvent:
    """Build a tool_call event."""
    return TracedEvent(
        event_id=str(uuid.uuid4()),
        session_id=session_id,
        agent_id=agent_id,
        user_id=user_id,
        sequence=sequence,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        type="tool_call",
        provider=agent_id,
        tool_name=tool_name,
        content=json.dumps(tool_input, ensure_ascii=False),
        duration_ms=duration_ms,
        metadata={"integration": integration},
    )


def build_tool_result_event(
    session_id: str,
    agent_id: str,
    sequence: int,
    tool_name: str,
    tool_output: str,
    duration_ms: int = 0,
    error: Optional[str] = None,
    status_code: int = 0,
    user_id: str = "",
    integration: str = "tracea-mcp",
) -> TracedEvent:
    """Build a tool_result or error event."""
    return TracedEvent(
        event_id=str(uuid.uuid4()),
        session_id=session_id,
        agent_id=agent_id,
        user_id=user_id,
        sequence=sequence,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        type="error" if error else "tool_result",
        provider=agent_id,
        tool_name=tool_name,
        content=tool_output[:2000] if tool_output else None,
        status_code=status_code if status_code else (1 if error else 0),
        error=error,
        duration_ms=duration_ms,
        metadata={"integration": integration},
    )


def build_session_end_event(
    session_id: str,
    agent_id: str,
    sequence: int,
    user_id: str = "",
    integration: str = "tracea-mcp",
) -> TracedEvent:
    """Build a session_end event."""
    return TracedEvent(
        event_id=str(uuid.uuid4()),
        session_id=session_id,
        agent_id=agent_id,
        user_id=user_id,
        sequence=sequence,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        type="session_end",
        provider=agent_id,
        metadata={"integration": integration},
    )
