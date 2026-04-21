"""Provider detection and URL utilities for httpx transport patching."""
from __future__ import annotations
from urllib.parse import urlparse
from tracea.events import Provider

# URL paths that indicate specific providers
OPENAI_PATHS = {"/v1/chat/completions", "/v1/completions"}
ANTHROPIC_PATHS = {"/v1/messages"}

def detect_provider(url: str) -> Provider:
    """Detect LLM provider from request URL path.

    Provider detection is BASE URL agnostic — strips the base URL
    and matches only on the API path. Works with Azure OpenAI,
    OpenAI proxies, and direct API URLs.
    """
    path = extract_path(url)
    if not path:
        return "unknown"

    # Normalize path (remove trailing slash)
    normalized = path.rstrip("/")

    # Check OpenAI paths
    if normalized in OPENAI_PATHS or "/v1/chat/completions" in normalized:
        return "openai"

    # Handle Azure OpenAI: /openai/deployments/{deployment}/chat/completions
    if normalized.startswith("/openai/deployments/"):
        return "openai"

    if normalized in ANTHROPIC_PATHS or "/v1/messages" in normalized:
        return "anthropic"

    return "unknown"

def extract_path(url: str) -> str:
    """Extract the path component from a URL, stripping base URL."""
    try:
        parsed = urlparse(url)
        return parsed.path
    except Exception:
        return ""

def build_url(base_url: str, path: str) -> str:
    """Build a full URL from base URL and path."""
    base = base_url.rstrip("/")
    return f"{base}{path}"
