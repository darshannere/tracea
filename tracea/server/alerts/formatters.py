"""Alert formatters: Slack Block Kit and generic HTTP webhook."""

import os
from datetime import datetime
from typing import Literal

_SEVERITY_BADGES = {
    "critical": ("[CRITICAL]", "danger"),
    "high": ("[HIGH]", "danger"),
    "medium": ("[MEDIUM]", "primary"),
    "low": ("[LOW]", "primary"),
}

_BASE_URL = os.getenv("TRACEA_BASE_URL", "http://localhost:8080")


def format_slack_blockkit(
    issue: dict,
    base_url: str | None = None,
    session_start: str | None = None,
) -> dict:
    """Build a Slack Block Kit payload from an issue dict.

    Args:
        issue: Issue dict with session_id, issue_type, severity, etc.
        base_url: Optional base URL override.
        session_start: Pre-fetched session start time string (ISO format or formatted).
                      If not provided, falls back to 'unknown'.
    """
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

    # Format session start time if provided
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
    """Route to the correct formatter based on route_type.

    Args:
        issue: Issue dict.
        route_type: "slack" or "http".
        base_url: Optional base URL override.
        session_start: Pre-fetched session start time for Slack formatter.
    """
    if route_type == "slack":
        return format_slack_blockkit(issue, base_url, session_start)
    else:
        return format_generic_webhook(issue, base_url)