"""tracea SDK configuration — singleton, env vars primary."""
from __future__ import annotations
import os
from dataclasses import dataclass, field

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

    # Env vars are primary; params override if provided
    resolved_api_key = api_key or os.environ.get("TRACEA_API_KEY", "")

    resolved_server_url = server_url or os.environ.get("TRACEA_SERVER_URL", "http://localhost:8080")
    resolved_base_url = base_url or os.environ.get("TRACEA_BASE_URL", resolved_server_url)
    resolved_user_id = user_id or os.environ.get("TRACEA_USER_ID", "")
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