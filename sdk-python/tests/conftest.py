"""Pytest configuration and fixtures for tracea tests."""
import pytest
import sys
import asyncio
import os
import httpx
import respx
from pathlib import Path

# Ensure the package is importable from the source
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def respx_mock():
    """Mock httpx requests to OpenAI API via respx.

    Installs a global respx mock that intercepts all https://api.openai.com/ requests.
    Tests can customize the mock response before making actual SDK calls.
    """
    import tracea.patch

    # Capture original patch state
    was_patched = tracea.patch._is_patched if hasattr(tracea.patch, '_is_patched') else False

    with respx.mock:
        # Default: all OpenAI API calls return a valid 200 response
        respx.route(method="POST", url__startswith="https://api.openai.com/").mock(
            return_value=httpx.Response(200, json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                "usage": {"total_tokens": 10, "prompt_tokens": 5, "completion_tokens": 5}
            })
        )
        yield respx.mock

    # Teardown: reset httpx patch state and config singleton
    if was_patched:
        tracea.patch.unpatch()
    else:
        try:
            tracea.patch.unpatch()
        except Exception:
            pass

    # Reset the config singleton
    import tracea.config
    tracea.config._config = None


@pytest.fixture
def tracea_init(respx_mock):
    """Initialize tracea SDK with test credentials and mocked server URL.

    The respx_mock fixture must come first to set up the mock before tracea.init()
    calls patch().
    """
    import tracea

    # Init tracea — this installs httpx patch on top of respx mock
    tracea.init(api_key="test-key", server_url="https://api.openai.com/")

    yield

    # Teardown: unpatch httpx
    try:
        tracea.patch.unpatch()
    except Exception:
        pass

    # Reset config singleton
    import tracea.config
    tracea.config._config = None
