"""Unit tests for httpx transport patches (PYS-02, PYS-03, PYS-04, PYS-06).

All tests here are pure unit tests — no server subprocess, no real network.
Events are captured by mocking _emit_event directly.
"""
import pytest
import httpx
import respx
from unittest.mock import patch as mock_patch
from uuid import uuid4


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_MSG_URL = "https://api.anthropic.com/v1/messages"

OPENAI_RESPONSE = {
    "id": "chatcmpl-unit",
    "object": "chat.completion",
    "choices": [{"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}],
    "usage": {"total_tokens": 5, "prompt_tokens": 2, "completion_tokens": 3},
}

ANTHROPIC_RESPONSE = {
    "id": "msg-unit",
    "type": "message",
    "role": "assistant",
    "content": [{"type": "text", "text": "hi"}],
    "usage": {"input_tokens": 2, "output_tokens": 3},
}


@pytest.fixture(autouse=True)
def clean_patch():
    """Guarantee httpx patch is removed before and after every test."""
    from tracea.patch.httpx import unpatch, _is_patched
    if _is_patched:
        unpatch()
    yield
    from tracea.patch.httpx import _is_patched as still_patched, unpatch as do_unpatch
    if still_patched:
        do_unpatch()


# ---------------------------------------------------------------------------
# PYS-02: class-level intercept
# ---------------------------------------------------------------------------

def test_patch_intercepts_openai():
    """PYS-02: httpx.Client.send patch intercepts openai chat completions call."""
    from tracea.patch.httpx import patch, unpatch

    captured = []

    with mock_patch("tracea.patch.httpx._emit_event", side_effect=lambda e: captured.append(e)):
        with respx.mock:
            respx.post(OPENAI_CHAT_URL).mock(return_value=httpx.Response(200, json=OPENAI_RESPONSE))

            patch()
            client = httpx.Client()
            resp = client.post(
                OPENAI_CHAT_URL,
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
            )
            unpatch()

    assert resp.status_code == 200
    assert len(captured) == 1, f"Expected 1 event, got {len(captured)}"
    ev = captured[0]
    assert ev.provider == "openai"
    assert ev.model == "gpt-4o"
    assert ev.status_code == 200
    assert ev.duration_ms >= 0


@pytest.mark.asyncio
async def test_patch_intercepts_anthropic_async():
    """PYS-02: httpx.AsyncClient.send patch intercepts anthropic async call."""
    from tracea.patch.httpx import patch, unpatch

    captured = []

    with mock_patch("tracea.patch.httpx._emit_event", side_effect=lambda e: captured.append(e)):
        with respx.mock:
            respx.post(ANTHROPIC_MSG_URL).mock(return_value=httpx.Response(200, json=ANTHROPIC_RESPONSE))

            patch()
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    ANTHROPIC_MSG_URL,
                    json={"model": "claude-3-5-sonnet-20241022", "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]},
                )
            unpatch()

    assert resp.status_code == 200
    assert len(captured) == 1, f"Expected 1 event, got {len(captured)}"
    ev = captured[0]
    assert ev.provider == "anthropic"
    assert ev.status_code == 200


# ---------------------------------------------------------------------------
# PYS-03: explicit per-client patch
# ---------------------------------------------------------------------------

def test_patch_explicit_client():
    """PYS-03: patch_client(client) patches already-constructed openai client."""
    from tracea.patch import patch_client
    from tracea.patch.httpx import _is_patched

    assert not _is_patched, "Class-level patch must be off for this test"

    # Build a minimal mock LLM-client with an httpx.Client at ._client
    http_client = httpx.Client()
    original_send = http_client.send  # bound method before patch

    class MockLLMClient:
        _client = http_client

    result = patch_client(MockLLMClient())
    assert result is True

    # Instance-level send should now be replaced
    assert http_client.send is not original_send, (
        "patch_client() must replace instance send when class-level patch is off"
    )

    http_client.close()


def test_patch_explicit_client_with_class_patch():
    """PYS-03: patch_client() returns True immediately when class-level patch is active."""
    from tracea.patch import patch_client
    from tracea.patch.httpx import patch, unpatch

    patch()

    http_client = httpx.Client()

    class MockLLMClient:
        _client = http_client

    result = patch_client(MockLLMClient())
    assert result is True  # class-level patch already covers it

    unpatch()
    http_client.close()


# ---------------------------------------------------------------------------
# PYS-04: provider detection
# ---------------------------------------------------------------------------

def test_provider_detection():
    """PYS-04: Provider detection returns correct provider from URL path."""
    from tracea.patch._utils import detect_provider
    assert detect_provider("https://api.openai.com/v1/chat/completions") == "openai"
    assert detect_provider("https://api.anthropic.com/v1/messages") == "anthropic"
    assert detect_provider("https://my-company.openai.azure.com/v1/chat/completions") == "openai"
    assert detect_provider("https://localhost:8080/v1/chat/completions") == "openai"
    assert detect_provider("https://example.com/other") == "unknown"


# ---------------------------------------------------------------------------
# PYS-06: Azure / proxy base URL support
# ---------------------------------------------------------------------------

def test_base_url_stripping():
    """PYS-06: Base URL is stripped before provider path matching."""
    from tracea.patch._utils import detect_provider
    assert detect_provider("https://my-azure.openai.azure.com/v1/chat/completions") == "openai"
    assert detect_provider("https://proxy.example.com/openai/v1/chat/completions") == "openai"


def test_azure_openai_path_detection():
    """PYS-06: Azure OpenAI deployment path is detected as openai provider."""
    from tracea.patch._utils import detect_provider
    assert detect_provider("https://my-azure.openai.azure.com/openai/deployments/gpt-4o/chat/completions") == "openai"
    assert detect_provider("https://my-resource.openai.azure.com/openai/deployments/gpt-4o-mini/chat/completions?api-version=2024-06-01") == "openai"


def test_is_llm_request_with_per_client_base_url():
    """PYS-06: Per-client base URL is used to strip prefix from request URL."""
    from tracea.patch.httpx import _is_llm_request

    url = "https://my-azure.openai.azure.com/openai/deployments/gpt-4o/chat/completions"
    request = httpx.Request("POST", url)

    assert _is_llm_request(request) is True

    class MockClient:
        _tracea_base_url = "https://my-azure.openai.azure.com"

    assert _is_llm_request(request, client=MockClient()) is True


def test_patch_client_stores_base_url():
    """PYS-06: patch_client(base_url=...) stores base URL on the http_client."""
    from tracea.patch import patch_client

    mock_http_client = httpx.Client(base_url="https://my-azure.openai.azure.com")
    mock_client = type("MockOpenAIClient", (), {"_client": mock_http_client})()

    result = patch_client(mock_client, base_url="https://my-azure.openai.azure.com")

    assert result is True
    assert hasattr(mock_http_client, "_tracea_base_url")
    assert mock_http_client._tracea_base_url == "https://my-azure.openai.azure.com"
    mock_http_client.close()


# ---------------------------------------------------------------------------
# PYS-02: patch hygiene
# ---------------------------------------------------------------------------

def test_patch_idempotent():
    """PYS-02: Calling patch() twice does not double-wrap."""
    from tracea.patch.httpx import patch, unpatch, _patched_sync_send

    patch()
    send_after_first = httpx.Client.send

    patch()  # second call — should be a no-op
    send_after_second = httpx.Client.send

    assert send_after_first is send_after_second is _patched_sync_send

    unpatch()


def test_unpatch_restores_original():
    """PYS-02: unpatch() restores original httpx send methods."""
    from tracea.patch.httpx import patch, unpatch, _patched_sync_send

    real_sync = httpx.Client.send
    real_async = httpx.AsyncClient.send

    patch()
    assert httpx.Client.send is _patched_sync_send
    assert httpx.AsyncClient.send is not real_async  # async patch installed

    unpatch()
    assert httpx.Client.send is real_sync
    assert httpx.AsyncClient.send is real_async
