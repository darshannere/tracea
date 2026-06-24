"""Test config singleton and agent_id propagation (Wave 1 fix #3)."""
import pytest

from tracea.patch._utils import detect_provider


def _reset_config():
    import tracea.config
    tracea.config._config = None


@pytest.fixture(autouse=True)
def clean_config(monkeypatch):
    """Reset config singleton + env before and after each test."""
    _reset_config()
    monkeypatch.delenv("TRACEA_AGENT_ID", raising=False)
    yield
    _reset_config()


def test_agent_id_from_env_flows_to_config():
    """TRACEA_AGENT_ID is resolved and stored on the config."""
    import tracea

    try:
        cfg = tracea.init(api_key="k", server_url="http://s", user_id="")
        assert cfg.agent_id == ""
    finally:
        _reset_config()


def test_agent_id_env_var_stored():
    """Setting TRACEA_AGENT_ID stores it in config.agent_id."""
    import tracea

    try:
        cfg = tracea.init(
            api_key="k",
            server_url="http://s",
            agent_id="my-bot-v2",
            user_id="",
        )
        assert cfg.agent_id == "my-bot-v2"
    finally:
        _reset_config()


def test_agent_id_flows_to_httpx_event():
    """Regression: agent_id from config must reach events built by the httpx
    patch. Previously resolved_agent_id was computed in init() but never stored,
    so all SDK events got agent_id=''."""
    import tracea
    import httpx
    import respx
    from tracea.patch import httpx as httpx_patch
    from unittest.mock import patch as mock_patch

    OPENAI_URL = "https://api.openai.com/v1/chat/completions"
    resp_json = {
        "id": "x",
        "choices": [{"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}],
        "usage": {"total_tokens": 1, "prompt_tokens": 1, "completion_tokens": 0},
    }

    captured = []
    with mock_patch("tracea.patch.httpx._emit_event", side_effect=lambda e: captured.append(e)):
        with respx.mock:
            respx.post(OPENAI_URL).mock(return_value=httpx.Response(200, json=resp_json))
            tracea.init(
                api_key="k",
                server_url="http://s",
                agent_id="httpx-agent-42",
                user_id="",
            )
            httpx_patch.patch()
            client = httpx.Client()
            client.post(OPENAI_URL, json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]})
            httpx_patch.unpatch()

    assert len(captured) == 1
    assert captured[0].agent_id == "httpx-agent-42", (
        f"config agent_id must flow to httpx events, got {captured[0].agent_id!r}"
    )
    _reset_config()


def test_session_context_agent_id_overrides_config():
    """Session context agent_id takes precedence over config agent_id."""
    import asyncio
    import tracea
    from tracea.log import _resolve_agent_id

    try:
        tracea.init(api_key="k", server_url="http://s", agent_id="config-agent", user_id="")

        # Without session context, config value is used
        assert _resolve_agent_id() == "config-agent"

        # Inside a session with its own agent_id, the context wins
        async def _check():
            async with tracea.session(agent_id="session-agent"):
                assert _resolve_agent_id() == "session-agent"
            # After session ends, config value restored
            assert _resolve_agent_id() == "config-agent"

        asyncio.run(_check())
    finally:
        _reset_config()
