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

        # Patch the underlying httpx client's send method directly
        from tracea.patch.httpx import _original_sync_send
        if hasattr(http_client, "send") and http_client.send is not _original_sync_send:
            # Already patched via class-level
            return True

        # Apply instance-level patch
        import tracea.patch.httpx as _httpx_patch
        http_client.send = lambda req, **kwargs: _httpx_patch._patched_sync_send(http_client, req, **kwargs)
        return True
    except Exception:
        return False

__all__ = ["patch", "unpatch", "patch_client"]
