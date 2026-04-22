from pydantic import BaseModel
from typing import Literal


class RCABackendConfig(BaseModel):
    """Configuration for RCA backend, driven by env vars."""
    backend: Literal["disabled", "ollama", "openai", "anthropic"] = "disabled"
    model: str | None = None  # e.g., "gpt-4o", "claude-sonnet-4"
    base_url: str | None = None  # for ollama/custom OpenAI compatible
    prompt_path: str | None = None  # TRACEA_RCA_PROMPT_PATH
    redact_content: bool = True  # rca_redact_content default True
    max_tokens: int = 2048  # max tokens for RCA response


class RCAContext(BaseModel):
    """Context sent to the LLM for root-cause analysis."""
    rule_id: str
    rule_description: str
    issue_category: str
    severity: str
    triggering_events: list[dict]  # event type, error, cost, duration, tool_name, model, sequence
    session_aggregates: dict  # cost, duration, event_count, input_tokens, output_tokens
    session_metadata: dict
    session_start_time: str | None = None
    # New verbose fields
    event_timeline: list[dict]  # chronology of events in session
    tool_breakdown: list[dict]  # tool usage stats
    model_breakdown: list[dict]  # model usage stats
    latency_stats: dict  # min, max, avg, p95 duration_ms
    related_issues: list[dict]  # other issues in same session
    historical_frequency: dict  # rule firing stats
    rule_config_snapshot: dict  # full rule configuration
