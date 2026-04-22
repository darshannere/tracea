"""Tests for tracea.log fire-and-forget helpers."""
from __future__ import annotations
import pytest
from tracea import log_tool_call, log_tool_result, log_chat, log_error, log_event, LogTool


class TestLogHelpers:
    """Tests for direct event logging helpers."""

    def test_log_tool_call(self, tracea_init):
        """log_tool_call should not raise."""
        log_tool_call("search", {"query": "python"})

    def test_log_tool_result(self, tracea_init):
        """log_tool_result should not raise."""
        log_tool_result("search", result={"hits": [1, 2, 3]}, duration_ms=120)

    def test_log_chat(self, tracea_init):
        """log_chat should not raise."""
        log_chat(role="assistant", content="Hello", model="gpt-4o")

    def test_log_error(self, tracea_init):
        """log_error should not raise."""
        log_error("Something went wrong")

    def test_log_event_custom(self, tracea_init):
        """log_event should not raise for arbitrary types."""
        log_event("custom.thing", content="hello", model="test-model")

    def test_log_tool_context_manager(self, tracea_init):
        """LogTool context manager should emit start + result events."""
        with LogTool("search", arguments={"query": "python"}) as lt:
            lt.result = {"hits": [1, 2, 3]}

    def test_log_tool_context_manager_error(self, tracea_init):
        """LogTool should capture exceptions as error events."""
        with pytest.raises(ValueError):
            with LogTool("search", arguments={"query": "python"}) as lt:
                raise ValueError("boom")

    def test_log_fire_and_forget_no_init(self):
        """Logging before init should not crash (silently drops)."""
        log_tool_call("search", {"query": "python"})
        log_error("test")

    def test_log_tool_build_event(self, tracea_init):
        """_build_event produces correct fields."""
        from tracea.log import _build_event

        event = _build_event(
            event_type="tool_call",
            tool_name="search",
            content='{"q": "x"}',
        )
        assert event.tool_name == "search"
        assert event.content == '{"q": "x"}'
        assert event.type == "tool_call"

    def test_resolve_session_id(self, tracea_init):
        """Session ID is resolved correctly."""
        from tracea.log import _resolve_session_id

        sid = _resolve_session_id()
        assert sid  # non-empty string

    def test_resolve_agent_id(self, tracea_init):
        """Agent ID is resolved correctly."""
        from tracea.log import _resolve_agent_id

        aid = _resolve_agent_id()
        # Empty string when no context
        assert isinstance(aid, str)

    def test_log_chat_with_provider(self, tracea_init):
        """log_chat accepts provider parameter."""
        log_chat(role="user", content="Hi", model="claude-3", provider="anthropic")

    def test_log_event_with_metadata(self, tracea_init):
        """log_event accepts metadata dict."""
        log_event("custom", content="test", metadata={"foo": "bar"})

    def test_log_tool_call_id_roundtrip(self, tracea_init):
        """tool_call_id is preserved between call and result."""
        import uuid
        tcid = str(uuid.uuid4())
        log_tool_call("fetch", {"url": "http://example.com"}, tool_call_id=tcid)
        log_tool_result("fetch", result="ok", tool_call_id=tcid)
