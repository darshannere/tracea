"""Alert models — Pydantic models for alert routing configuration."""

from pydantic import BaseModel
from typing import Literal


class AlertRoute(BaseModel):
    """A single route: which issue_category goes to which webhook."""
    issue_category: str  # e.g., "tool_error" or "*" for default
    route_type: Literal["slack", "http"]
    webhook_url: str
    # Rate limit config (per destination)
    rate_limit_rpm: int = 60  # messages per minute, default 60 (= 1/sec)


class AlertsConfig(BaseModel):
    """Top-level alerts.yaml structure."""
    routes: list[AlertRoute]


def load_alerts_config(path: str) -> AlertsConfig:
    """Load alerts.yaml from path."""
    import ruamel.yaml
    with open(path) as f:
        data = ruamel.yaml.YAML().load(f)
    return AlertsConfig(**data)