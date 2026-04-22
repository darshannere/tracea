from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime
class TokenUsage(BaseModel):
    input: int = 0
    output: int = 0
    total: int = 0


EventType = Literal["session_start", "chat.completion", "tool_call", "tool_result", "error", "session_end"]


class TracedEvent(BaseModel):
    event_id: str
    session_id: str
    agent_id: str
    sequence: int = 0
    timestamp: datetime
    type: EventType
    provider: Literal[
        "openai", "anthropic", "azure_openai", "ollama",
        "claude-code", "gemini-cli", "opencode", "tracea-mcp", "kimi",
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
