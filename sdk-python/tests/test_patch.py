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

def test_azure_openai_path_detection():
    """PYS-06: Azure OpenAI deployment path is detected as openai provider."""
    from tracea.patch._utils import detect_provider
    # Azure OpenAI uses /openai/deployments/{deployment}/chat/completions
    assert detect_provider("https://my-azure.openai.azure.com/openai/deployments/gpt-4o/chat/completions") == "openai"
    assert detect_provider("https://my-resource.openai.azure.com/openai/deployments/gpt-4o-mini/chat/completions?api-version=2024-06-01") == "openai"

def test_is_llm_request_with_per_client_base_url():
    """PYS-06: Per-client base URL is used to strip prefix from request URL."""
    from tracea.patch.httpx import _is_llm_request

    # Simulate an httpx Request to Azure OpenAI
    url = "https://my-azure.openai.azure.com/openai/deployments/gpt-4o/chat/completions"
    request = httpx.Request("POST", url)

    # Without client base_url: returns unknown (path is not recognized as standard openai)
    assert _is_llm_request(request) is False

    # With client base_url set on a mock client: correctly detects as openai
    class MockClient:
        _tracea_base_url = "https://my-azure.openai.azure.com"

    assert _is_llm_request(request, client=MockClient()) is True

def test_patch_client_stores_base_url():
    """PYS-06: patch_client(base_url=...) stores base URL on the http_client."""
    from tracea.patch import patch_client

    # Create a mock openai-like client with an httpx client inside
    mock_http_client = httpx.Client(base_url="https://my-azure.openai.azure.com")
    mock_client = type("MockOpenAIClient", (), {"_client": mock_http_client})()

    # patch_client with base_url should store it on the http_client
    result = patch_client(mock_client, base_url="https://my-azure.openai.azure.com")

    assert result is True
    assert hasattr(mock_http_client, "_tracea_base_url")
    assert mock_http_client._tracea_base_url == "https://my-azure.openai.azure.com"

def test_patch_idempotent():
    """PYS-02: Calling patch() twice does not double-wrap."""
    # TODO: Call patch() twice, verify send is only wrapped once
    pass

def test_unpatch_restores_original():
    """PYS-02: unpatch() restores original httpx send methods."""
    # TODO: Patch, unpatch, verify original is restored
    pass
