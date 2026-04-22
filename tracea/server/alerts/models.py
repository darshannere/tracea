"""Alert models — Pydantic models for alert routing configuration."""

import os
import re
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


_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


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
    import ruamel.yaml
    with open(path) as f:
        data = ruamel.yaml.YAML().load(f)
    data = _expand_env_vars(data)
    return AlertsConfig(**data)
