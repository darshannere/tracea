"""Event schema dataclasses matching tracea server EventBatch schema.

Uses stdlib dataclasses instead of pydantic to avoid version conflicts
in user environments that may pin pydantic<2.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Optional
from datetime import datetime
from uuid import UUID

@dataclass
class TokenUsage:
    input: int = 0
    output: int = 0
    total: int = 0

EventType = Literal["session_start", "chat.completion", "tool_call", "tool_result", "error", "session_end"]
Provider = Literal["openai", "anthropic", "azure_openai", "ollama", "unknown"]
Role = Literal["user", "assistant", "system"]

@dataclass
class TracedEvent:
    event_id: UUID
    session_id: UUID
    agent_id: str
    sequence: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    type: EventType = "chat.completion"
    provider: Provider = "unknown"
    model: str = ""
    role: Optional[Role] = None
    content: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    status_code: Optional[int] = None
    error: Optional[str] = None
    duration_ms: int = 0
    tokens_used: Optional[TokenUsage] = None
    cost_usd: Optional[float] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "event_id": str(self.event_id),
            "session_id": str(self.session_id),
            "agent_id": self.agent_id,
            "sequence": self.sequence,
            "timestamp": self.timestamp.isoformat(),
            "type": self.type,
            "provider": self.provider,
            "model": self.model,
            "role": self.role,
            "content": self.content,
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "status_code": self.status_code,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "cost_usd": self.cost_usd,
            "metadata": self.metadata,
        }
        if self.tokens_used:
            d["tokens_used"] = {
                "input": self.tokens_used.input,
                "output": self.tokens_used.output,
                "total": self.tokens_used.total,
            }
        else:
            d["tokens_used"] = None
        return d

@dataclass
class EventBatch:
    events: list[TracedEvent]
    batch_id: Optional[UUID] = None

    def to_dict(self) -> dict:
        return {
            "events": [e.to_dict() for e in self.events],
            "batch_id": str(self.batch_id) if self.batch_id else None,
        }