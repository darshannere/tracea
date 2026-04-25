from pydantic import BaseModel, Field, model_validator
from typing import Literal, Optional
from datetime import datetime
class TokenUsage(BaseModel):
    input: int = 0
    output: int = 0
    total: int = 0

    @model_validator(mode="after")
    def check_token_consistency(self):
        if self.input + self.output > self.total + 2:  # Allow small rounding tolerance
            raise ValueError(f"input ({self.input}) + output ({self.output}) must not exceed total ({self.total})")
        return self


EventType = Literal[
    "session_start", "chat.completion", "tool_call", "tool_result", "error", "session_end",
    "agent_turn", "heartbeat", "memory_compaction", "gateway_event",
]


class TracedEvent(BaseModel):
    event_id: str
    session_id: str
    agent_id: str
    user_id: str = ""
    sequence: int = 0
    timestamp: datetime
    type: EventType
    provider: Literal[
        "openai", "anthropic", "azure_openai", "ollama",
        "claude-code", "gemini-cli", "opencode", "tracea-mcp", "kimi",
        "openclaw",
        "unknown",
    ] = "unknown"
    model: str = ""
    role: Optional[Literal["user", "assistant", "system"]] = None
    content: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    status_code: Optional[int] = None
    error: Optional[str] = None
    duration_ms: int = 0
    tokens_used: Optional[TokenUsage] = None
    cost_usd: Optional[float] = None
    metadata: dict = Field(default_factory=dict)

    model_config = {"str_strip_whitespace": True}


class EventBatch(BaseModel):
    events: list[TracedEvent]
    batch_id: Optional[str] = None
