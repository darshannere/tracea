"""tracea SDK configuration — singleton, env vars primary, config file fallback."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from tracea.config_loader import discover_config

@dataclass
class TraceaConfig:
    api_key: str
    server_url: str
    base_url: str  # TRACEA_BASE_URL — defaults to server_url for proxy support
    user_id: str = ""  # Team member identifier for multi-user dashboards
    metadata: dict = field(default_factory=dict)  # PYS-10: init-level metadata
    tags: list[str] = field(default_factory=list)  # PYS-10: init-level tags
    _initialized: bool = field(default=False, repr=False)

_config: TraceaConfig | None = None

def init(
    api_key: str | None = None,
    server_url: str | None = None,
    base_url: str | None = None,
    user_id: str | None = None,
    metadata: dict | None = None,
    tags: list[str] | None = None,
) -> TraceaConfig:
    """Initialize tracea SDK. Raises RuntimeError if called twice."""
    global _config

    if _config is not None:
        raise RuntimeError("tracea.init() already called")

    # Resolution order: explicit param → env var → config file → default
    discovered = discover_config()

    def _resolve(param, env_name, config_key, default=""):
        if param is not None:
            return param
        env_val = os.environ.get(env_name)
        if env_val is not None:
            return env_val
        return discovered.get(config_key, default)

    resolved_api_key = _resolve(api_key, "TRACEA_API_KEY", "api_key", "")
    resolved_server_url = _resolve(server_url, "TRACEA_SERVER_URL", "server_url", "http://localhost:8080")
    resolved_base_url = _resolve(base_url, "TRACEA_BASE_URL", "base_url", resolved_server_url)
    resolved_user_id = _resolve(user_id, "TRACEA_USER_ID", "user_id", "")
    resolved_agent_id = _resolve(None, "TRACEA_AGENT_ID", "agent_id", "")
    resolved_metadata = metadata or {}
    resolved_tags = tags or []

    _config = TraceaConfig(
        api_key=resolved_api_key,
        server_url=resolved_server_url,
        base_url=resolved_base_url,
        user_id=resolved_user_id,
        metadata=resolved_metadata,
        tags=resolved_tags,
    )
    _config._initialized = True
    return _config

def get_config() -> TraceaConfig:
    """Return the singleton config. Raises if not initialized."""
    if _config is None:
        raise RuntimeError("tracea.init() must be called before get_config()")
    return _config