"""Alert models, formatters, and backoff utility."""

import os
import re
import random
from datetime import datetime
from typing import Literal
from pydantic import BaseModel
import ruamel.yaml

_SEVERITY_BADGES = {
    "critical": ("[CRITICAL]", "danger"),
    "high": ("[HIGH]", "danger"),
    "medium": ("[MEDIUM]", "primary"),
    "low": ("[LOW]", "primary"),
}

_BASE_URL = os.getenv("TRACEA_BASE_URL", "http://localhost:8080")
_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


class AlertRoute(BaseModel):
    """A single route: which issue_category goes to which webhook."""
    issue_category: str  # e.g., "tool_error" or "*" for default
    route_type: Literal["slack", "http"]
    webhook_url: str
    rate_limit_rpm: int = 60  # messages per minute, default 60 (= 1/sec)


class AlertsConfig(BaseModel):
    """Top-level alerts.yaml structure."""
    routes: list[AlertRoute]


def _expand_env_vars(obj):
    """Recursively expand ${VAR} placeholders in strings using os.environ."""
    if isinstance(obj, str):
        def _replacer(match):
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))
        return _ENV_VAR_PATTERN.sub(_replacer, obj)
    if isinstance(obj, dict):
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env_vars(item) for item in obj]
    return obj


def load_alerts_config(path: str) -> AlertsConfig:
    """Load alerts.yaml from path, expanding ${ENV_VAR} placeholders."""
    with open(path) as f:
        data = ruamel.yaml.YAML().load(f)
    data = _expand_env_vars(data)
    return AlertsConfig(**data)


def format_slack_blockkit(
    issue: dict,
    base_url: str | None = None,
    session_start: str | None = None,
) -> dict:
    """Build a Slack Block Kit payload from an issue dict."""
    url = base_url or _BASE_URL
    session_id = issue.get("session_id", "")
    severity = issue.get("severity", "medium")
    issue_category = issue.get("issue_type", "")
    issue_id = issue.get("issue_id", "")
    cost = issue.get("session_cost_total", 0)
    duration = issue.get("session_duration_ms", 0)
    event_count = issue.get("session_event_count", 0)
    error_msg = issue.get("error_message", "") or "none"
    detected_at = issue.get("detected_at", "")

    badge, color = _SEVERITY_BADGES.get(severity, ("[MEDIUM]", "warning"))

    if session_start and session_start != "unknown":
        try:
            dt = datetime.fromisoformat(session_start.replace("Z", "+00:00"))
            session_start = dt.strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            pass
    else:
        session_start = session_start or "unknown"

    deep_link = f"{url}/sessions/{session_id}"

    return {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{badge} {issue_category}*\n_Session {session_id} — {session_start}_",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Cost:*\n${cost:.4f}"},
                    {"type": "mrkdwn", "text": f"*Duration:*\n{duration}ms"},
                    {"type": "mrkdwn", "text": f"*Events:*\n{event_count}"},
                    {"type": "mrkdwn", "text": f"*First Error:*\n{error_msg}"},
                ],
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View Session"},
                        "url": deep_link,
                        "style": color,
                    }
                ],
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"tracea | Issue ID: {issue_id} | {detected_at}",
                    }
                ],
            },
        ]
    }


def format_generic_webhook(issue: dict, base_url: str | None = None) -> dict:
    """Build a generic HTTP webhook JSON payload from an issue dict."""
    url = base_url or _BASE_URL
    session_id = issue.get("session_id", "")

    return {
        "event": "tracea.issue",
        "issue_id": issue.get("issue_id", ""),
        "session_id": session_id,
        "issue_category": issue.get("issue_type", ""),
        "severity": issue.get("severity", "medium"),
        "rule_id": issue.get("rule_id", ""),
        "rule_description": issue.get("rule_description", ""),
        "error_message": issue.get("error_message", ""),
        "session": {
            "cost_usd": issue.get("session_cost_total", 0),
            "duration_ms": issue.get("session_duration_ms", 0),
            "event_count": issue.get("session_event_count", 0),
        },
        "deep_link": f"{url}/sessions/{session_id}",
        "detected_at": issue.get("detected_at", ""),
    }


def format_alert_payload(
    issue: dict,
    route_type: Literal["slack", "http"],
    base_url: str | None = None,
    session_start: str | None = None,
) -> dict:
    """Route to the correct formatter based on route_type."""
    if route_type == "slack":
        return format_slack_blockkit(issue, base_url, session_start)
    else:
        return format_generic_webhook(issue, base_url)


def sync_exponential_backoff_with_jitter(
    attempt: int,
    base: float = 2.0,
    max_delay: float = 30.0,
    jitter_ratio: float = 0.5,
) -> float:
    """Synchronous version for non-async contexts."""
    delay = min(base * (2 ** attempt), max_delay)
    jitter = random.uniform(0, delay * jitter_ratio)
    return delay + jitter


async def exponential_backoff_with_jitter(
    attempt: int,
    base: float = 2.0,
    max_delay: float = 30.0,
    jitter_ratio: float = 0.5,
) -> float:
    """Calculate sleep time for exponential backoff with jitter."""
    return sync_exponential_backoff_with_jitter(attempt, base, max_delay, jitter_ratio)
