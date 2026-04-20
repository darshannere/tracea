from pydantic import BaseModel
from typing import Literal


class RCABackendConfig(BaseModel):
    """Configuration for RCA backend, driven by env vars."""
    backend: Literal["disabled", "ollama", "openai", "anthropic"] = "disabled"
    model: str | None = None  # e.g., "gpt-4o", "claude-sonnet-4"
    base_url: str | None = None  # for ollama/custom OpenAI compatible
    prompt_path: str | None = None  # TRACEA_RCA_PROMPT_PATH
    redact_content: bool = True  # rca_redact_content default True


class RCAContext(BaseModel):
    """Context sent to the LLM for root-cause analysis."""
    rule_id: str
    rule_description: str
    issue_category: str
    severity: str
    triggering_events: list[dict]  # event type, error, cost, duration, tool_name
    session_aggregates: dict  # cost, duration, event_count
    session_metadata: dict
