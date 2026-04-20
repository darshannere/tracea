"""Unit tests for httpx transport patches (PYS-02, PYS-03, PYS-04, PYS-06)."""
import pytest
import httpx
from uuid import uuid4

def test_patch_intercepts_openai():
    """PYS-02: httpx.Client.send patch intercepts openai chat completions call."""
    # TODO: Implement with respx mock
    # 1. Patch httpx
    # 2. Make request to fake openai endpoint
    # 3. Verify event was emitted
    pass

@pytest.mark.asyncio
async def test_patch_intercepts_anthropic_async():
    """PYS-02: httpx.AsyncClient.send patch intercepts anthropic async call."""
    # TODO: Implement with respx mock
    pass

def test_patch_explicit_client():
    """PYS-03: tracea.patch(client) patches already-constructed openai client."""
    # TODO: Create httpx.Client, call patch_client(), verify send is patched
    pass

def test_provider_detection():
    """PYS-04: Provider detection returns correct provider from URL path."""
    from tracea.patch._utils import detect_provider
    assert detect_provider("https://api.openai.com/v1/chat/completions") == "openai"
    assert detect_provider("https://api.anthropic.com/v1/messages") == "anthropic"
    assert detect_provider("https://my-company.openai.azure.com/v1/chat/completions") == "openai"
    assert detect_provider("https://localhost:8080/v1/chat/completions") == "openai"
    assert detect_provider("https://example.com/other") == "unknown"

def test_base_url_stripping():
    """PYS-06: Base URL is stripped before provider path matching."""
    from tracea.patch._utils import detect_provider
    # Azure, proxies, custom endpoints all work
    assert detect_provider("https://my-azure.openai.azure.com/v1/chat/completions") == "openai"
    assert detect_provider("https://proxy.example.com/openai/v1/chat/completions") == "openai"

def test_patch_idempotent():
    """PYS-02: Calling patch() twice does not double-wrap."""
    # TODO: Call patch() twice, verify send is only wrapped once
    pass

def test_unpatch_restores_original():
    """PYS-02: unpatch() restores original httpx send methods."""
    # TODO: Patch, unpatch, verify original is restored
    pass
