"""tracea SDK HTTP transport patching."""
from tracea.patch.httpx import patch, unpatch

def patch_client(client, base_url: str | None = None):
    """Explicitly patch an already-constructed LLM client.

    Use this when the client was constructed before tracea.init() was called,
    or when a custom http_client was passed to the constructor.

    Args:
        client: An openai.OpenAI or anthropic.Anthropic client instance.
        base_url: Optional per-client base URL override for provider detection.
                  For Azure OpenAI and other proxied endpoints where the httpx
                  client has a custom base_url set, pass that base URL here so
                  the provider detection can correctly identify the provider from
                  the request path.

    Returns:
        True if patching succeeded, False otherwise.
    """
    try:
        # openai-python >= 1.0: client._client is the httpx.Client
        http_client = getattr(client, "_client", None)
        if http_client is None:
            return False

        # Store per-client base URL on the http_client for provider detection
        if base_url is not None:
            http_client._tracea_base_url = base_url

        # Reach the already-cached module to read live _is_patched and _patched_sync_send.
        import sys as _sys
        _httpx_mod = _sys.modules.get("tracea.patch.httpx")
        if _httpx_mod is None:
            raise RuntimeError("tracea.patch.httpx not yet loaded")

        # If class-level patch is active, all httpx.Client instances are already covered.
        if _httpx_mod._is_patched:
            return True

        # Class-level patch not active — apply an instance-level send patch.
        _psend = _httpx_mod._patched_sync_send
        http_client.send = lambda req, **kwargs: _psend(http_client, req, **kwargs)
        return True
    except Exception as _e:
        import logging as _log
        _log.getLogger("tracea").warning(f"patch_client failed: {_e!r}")
        return False

__all__ = ["patch", "unpatch", "patch_client"]
