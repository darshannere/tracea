"""Alert payload formatters for different route types."""

import time
from typing import Literal


def format_alert_payload(issue: dict, route_type: Literal["slack", "http"], base_url: str) -> dict:
    """Build the webhook payload based on route type."""
    issue_id = issue.get("issue_id", "")
    session_id = issue.get("session_id", "")
    issue_category = issue.get("issue_type", "")
    severity = issue.get("severity", "medium")
    error_msg = issue.get("error_message", "")

    if route_type == "slack":
        # Slack Block Kit payload
        severity_emoji = {
            "critical": ":rotating_light:",
            "high": ":warning:",
            "medium": ":large_yellow_circle:",
            "low": ":large_blue_circle:",
        }.get(severity, ":large_yellow_circle:")

        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{severity_emoji} Tracea Alert: {issue_category}",
                        "emoji": True,
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Issue:*\n{issue_category}"},
                        {"type": "mrkdwn", "text": f"*Severity:*\n{severity}"},
                        {"type": "mrkdwn", "text": f"*Session:*\n{session_id[:8]}..."},
                        {"type": "mrkdwn", "text": f"*Issue ID:*\n{issue_id[:8]}..."},
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Error:*\n```{error_msg[:500]}```" if error_msg else None
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View in Tracea"},
                            "url": f"{base_url}/static/index.html?session={session_id}&issue={issue_id}",
                            "action_id": "view_issue"
                        }
                    ]
                }
            ],
            "issue_id": issue_id,
            "session_id": session_id,
            "issue_category": issue_category,
            "severity": severity,
            "ts": int(time.time()),
        }
    else:
        # Generic HTTP JSON payload
        return {
            "event_type": "tracea.alert",
            "issue_id": issue_id,
            "session_id": session_id,
            "issue_type": issue_category,
            "severity": severity,
            "error_message": error_msg,
            "url": f"{base_url}/static/index.html?session={session_id}&issue={issue_id}",
            "timestamp": int(time.time()),
        }