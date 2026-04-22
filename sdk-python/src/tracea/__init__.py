"""tracea — self-hosted AI agent observability SDK.

Two-line integration:
    pip install tracea
    tracea.init(api_key="...", server_url="...")

For explicit session management:
    async with tracea.session(metadata={"user_id": "123"}):
        response = client.chat.completions.create(...)

For patching already-constructed clients:
    tracea.patch_client(openai_client)

For direct event logging (fire-and-forget):
    tracea.log_tool_call("search", {"query": "python"})
    tracea.log_tool_result("search", result={"hits": [...]}, duration_ms=120)
    tracea.log_chat(role="assistant", content="Hello", model="gpt-4o")
    tracea.log_error("Something went wrong")

For auto-timed tool calls:
    with tracea.LogTool("search", arguments={"query": "python"}) as lt:
        lt.result = do_search("python")
"""
from tracea.config import init, get_config
from tracea.session import session, derive_session_id, get_session_ctx
from tracea.patch import patch, unpatch, patch_client
from tracea.buffer import get_buffer
from tracea.events import TracedEvent, EventBatch, TokenUsage
from tracea.api import TraceaAPIClient
from tracea.log import (
    log_tool_call,
    log_tool_result,
    log_chat,
    log_error,
    log_event,
    LogTool,
)

__all__ = [
    # Configuration
    "init",
    "get_config",
    # Session management
    "session",
    "derive_session_id",
    "get_session_ctx",
    # Transport patching
    "patch",
    "unpatch",
    "patch_client",
    # Buffer
    "get_buffer",
    # Event schema
    "TracedEvent",
    "EventBatch",
    "TokenUsage",
    # API client
    "TraceaAPIClient",
    # Direct logging (fire-and-forget)
    "log_tool_call",
    "log_tool_result",
    "log_chat",
    "log_error",
    "log_event",
    "LogTool",
]

def init(
    api_key: str | None = None,
    server_url: str | None = None,
    base_url: str | None = None,
    metadata: dict | None = None,
    tags: list[str] | None = None,
):
    """Initialize the tracea SDK.

    This must be called once at application startup, before any LLM calls.
    Installs httpx transport patches automatically.

    Args:
        api_key: Your tracea API key. Defaults to TRACEA_API_KEY env var.
        server_url: Your tracea server URL. Defaults to TRACEA_SERVER_URL env var
                    or "http://localhost:8080".
        base_url: Base URL for LLM API calls (for Azure OpenAI, proxies, etc.).
                  Defaults to TRACEA_BASE_URL env var or server_url.
        metadata: Global metadata applied to all events.
        tags: Global tags applied to all events.

    Raises:
        RuntimeError: If called more than once.
        ValueError: If api_key is not set via param or env var.
    """
    # Import here to avoid circular deps
    from tracea.config import init as _init
    cfg = _init(
        api_key=api_key,
        server_url=server_url,
        base_url=base_url,
        metadata=metadata,
        tags=tags,
    )

    # Auto-patch httpx after init
    patch()

    return cfg
