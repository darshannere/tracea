"""RCA prompt construction. Redacts user content by default."""

import json

from tracea.server.rca.models import RCAContext

DEFAULT_PROMPT = """You are a DevOps root-cause analyst specializing in AI agent observability. Given the following comprehensive issue context, produce a thorough root-cause analysis.

## Detection Rule
- ID: {rule_id}
- Description: {rule_description}
- Category: {issue_category}
- Severity: {severity}

## Triggering Event
{triggering_events}

## Session Overview
- Session started: {session_start_time}
- Total Cost: ${cost_usd}
- Total Duration: {duration_ms}ms
- Event Count: {event_count}
- Input Tokens: {input_tokens}
- Output Tokens: {output_tokens}

## Session Latency Stats
{latency_stats}

## Tool Usage Breakdown
{tool_breakdown}

## Model Usage Breakdown
{model_breakdown}

## Event Timeline (chronological, trigger marked with ★)
{event_timeline}

## Related Issues in This Session
{related_issues}

## Historical Frequency (last 24h)
{historical_frequency}

## Rule Configuration Snapshot
{rule_config_snapshot}

## Session Metadata
{session_metadata}

---

Provide a detailed root-cause analysis with the following sections. Be specific and cite evidence from the data above.

### 1. Problem Summary
A clear, one-paragraph summary of what happened and why it matters.

### 2. Evidence
Bullet points of concrete evidence from the session data that supports the diagnosis. Reference specific events, tools, models, or patterns.

### 3. Likely Root Cause
Your primary hypothesis for what caused this issue. Explain the chain of events or configuration that led to the failure. Be specific — name tools, models, or patterns.

### 4. Contributing Factors
Other factors that made this issue more likely or worse (e.g., model choice, repeated tool calls, high latency).

### 5. Recommended Actions
Specific, actionable recommendations to prevent this from recurring. Include prompt changes, tool configuration fixes, or model switches where relevant.

### 6. Confidence Level
State your confidence as Low / Medium / High and briefly explain why.

---

After your analysis, output a structured JSON block (wrapped in ```json) with the following fields for programmatic consumption:

```json
{{
  "summary": "one-line summary",
  "root_cause": "primary hypothesis",
  "contributing_factors": ["factor 1", "factor 2"],
  "recommended_actions": ["action 1", "action 2"],
  "confidence": "High|Medium|Low",
  "key_evidence": ["evidence 1", "evidence 2"]
}}
```
"""


def build_rca_prompt(context: RCAContext, prompt_template: str | None = None) -> str:
    """Build the prompt string from context and optional custom template."""
    template = prompt_template or DEFAULT_PROMPT

    # Format triggering events
    events_lines = []
    for ev in context.triggering_events:
        events_lines.append(
            f"- type={ev.get('type')}, error={ev.get('error')}, "
            f"cost=${ev.get('cost_usd', 0):.4f}, duration={ev.get('duration_ms', 0)}ms, "
            f"tool={ev.get('tool_name', 'n/a')}, model={ev.get('model', 'n/a')}, seq={ev.get('sequence', 0)}"
        )

    # Format latency stats
    ls = context.latency_stats
    latency_lines = [
        f"- Min: {ls.get('min_ms', 0)}ms",
        f"- Max: {ls.get('max_ms', 0)}ms",
        f"- Avg: {ls.get('avg_ms', 0)}ms",
        f"- P95: {ls.get('p95_ms', 0)}ms",
    ]

    # Format tool breakdown
    tool_lines = []
    for t in context.tool_breakdown:
        tool_lines.append(
            f"- {t.get('tool_name')}: {t.get('call_count')} calls, "
            f"{t.get('error_count')} errors, avg {t.get('avg_duration_ms')}ms, "
            f"${t.get('total_cost_usd', 0):.6f}"
        )
    if not tool_lines:
        tool_lines = ["- No tool calls recorded"]

    # Format model breakdown
    model_lines = []
    for m in context.model_breakdown:
        model_lines.append(
            f"- {m.get('model')}: {m.get('call_count')} calls, "
            f"{m.get('total_input_tokens')} input / {m.get('total_output_tokens')} output tokens, "
            f"${m.get('total_cost_usd', 0):.6f}"
        )
    if not model_lines:
        model_lines = ["- No model calls recorded"]

    # Format event timeline
    timeline_lines = []
    for ev in context.event_timeline:
        marker = " ★ TRIGGER" if ev.get("is_trigger") else ""
        timeline_lines.append(
            f"  seq={ev.get('sequence')} | {ev.get('type')} | "
            f"tool={ev.get('tool_name') or '-'} | model={ev.get('model') or '-'} | "
            f"cost=${ev.get('cost_usd', 0):.4f} | dur={ev.get('duration_ms', 0)}ms | "
            f"err={ev.get('error') or '-'}{marker}"
        )

    # Format related issues
    related_lines = []
    for ri in context.related_issues:
        related_lines.append(
            f"- [{ri.get('severity')}] {ri.get('issue_type')} at {ri.get('detected_at')} (rca={ri.get('rca_status')})"
        )
    if not related_lines:
        related_lines = ["- No other issues in this session"]

    # Format historical frequency
    hf = context.historical_frequency
    hist_lines = [
        f"- Rule '{context.rule_id}' fired {hf.get('count_24h', 0)} times in the last 24h",
        f"- Affected {hf.get('affected_sessions', 0)} unique sessions",
    ]

    return template.format(
        rule_id=context.rule_id,
        rule_description=context.rule_description,
        issue_category=context.issue_category,
        severity=context.severity,
        triggering_events="\n".join(events_lines) or "(none)",
        cost_usd=context.session_aggregates.get("cost_usd", 0),
        duration_ms=context.session_aggregates.get("duration_ms", 0),
        event_count=context.session_aggregates.get("event_count", 0),
        input_tokens=context.session_aggregates.get("input_tokens", 0),
        output_tokens=context.session_aggregates.get("output_tokens", 0),
        session_start_time=context.session_start_time or "(unknown)",
        latency_stats="\n".join(latency_lines),
        tool_breakdown="\n".join(tool_lines),
        model_breakdown="\n".join(model_lines),
        event_timeline="\n".join(timeline_lines) or "(none)",
        related_issues="\n".join(related_lines),
        historical_frequency="\n".join(hist_lines),
        rule_config_snapshot=json.dumps(context.rule_config_snapshot, indent=2) if context.rule_config_snapshot else "(none)",
        session_metadata=json.dumps(context.session_metadata, indent=2) if context.session_metadata else "(none)",
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
