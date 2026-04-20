"""RCA prompt construction. Redacts user content by default."""

from tracea.server.rca.models import RCAContext

DEFAULT_PROMPT = """You are a DevOps root-cause analyst. Given the following issue context, explain what likely caused it.

Rule: {rule_id} — {rule_description}
Issue Category: {issue_category}
Severity: {severity}

Triggering Events:
{triggering_events}

Session Aggregates:
- Total Cost: ${cost_usd}
- Total Duration: {duration_ms}ms
- Event Count: {event_count}

Session Metadata:
{session_metadata}

Provide a concise root-cause analysis in 2-3 sentences. Focus on observable symptoms, not speculation.
"""


def build_rca_prompt(context: RCAContext, prompt_template: str | None = None) -> str:
    """Build the prompt string from context and optional custom template."""
    template = prompt_template or DEFAULT_PROMPT

    # Format triggering events
    events_lines = []
    for ev in context.triggering_events:
        # Redact content field — only send metadata (type, error, cost_usd, duration_ms, tool_name)
        events_lines.append(
            f"- type={ev.get('type')}, error={ev.get('error')}, "
            f"cost=${ev.get('cost_usd', 0):.4f}, duration={ev.get('duration_ms', 0)}ms, "
            f"tool_name={ev.get('tool_name', 'n/a')}"
        )

    return template.format(
        rule_id=context.rule_id,
        rule_description=context.rule_description,
        issue_category=context.issue_category,
        severity=context.severity,
        triggering_events="\n".join(events_lines) or "(none)",
        cost_usd=context.session_aggregates.get("cost_usd", 0),
        duration_ms=context.session_aggregates.get("duration_ms", 0),
        event_count=context.session_aggregates.get("event_count", 0),
        session_metadata=str(context.session_metadata) if context.session_metadata else "(none)",
    )


def load_custom_prompt(path: str | None) -> str | None:
    """Load custom prompt from file path. Returns None if file not found."""
    if not path:
        return None
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return None
