"""Base tool handler."""
import time
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ToolResult:
    """Result from a tool execution."""
    success: bool
    content: str
    error: str | None = None
    exit_code: int = 0


class BaseTool(ABC):
    """Base class for MCP tool handlers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """MCP tool name."""
        raise NotImplementedError

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description."""
        raise NotImplementedError

    @property
    def input_schema(self) -> dict:
        """JSON Schema for tool input arguments."""
        return {"type": "object", "properties": {}, "required": []}

    @abstractmethod
    async def execute(self, args: dict) -> ToolResult:
        """Execute the tool with given arguments. Returns result."""
        raise NotImplementedError

    async def log_and_execute(self, args: dict, session_id: str, agent_id: str,
                               sequence_fn, event_post_fn, user_id: str = ""):
        """Execute tool, build events, post to tracea, return MCP result."""
        start = time.monotonic()

        # Emit tool_call event
        seq = sequence_fn()
        call_event = {
            "event_id": self._make_uuid(),
            "session_id": session_id,
            "agent_id": agent_id,
            "user_id": user_id,
            "sequence": seq,
            "timestamp": self._now(),
            "type": "tool_call",
            "provider": agent_id,
            "tool_name": self.name,
            "content": json.dumps(args, ensure_ascii=False),
            "duration_ms": 0,
            "metadata": {"integration": "tracea-mcp"},
        }

        # Execute tool
        result = await self.execute(args)
        duration_ms = int((time.monotonic() - start) * 1000)

        # Emit result event
        seq2 = sequence_fn()
        result_event = {
            "event_id": self._make_uuid(),
            "session_id": session_id,
            "agent_id": agent_id,
            "user_id": user_id,
            "sequence": seq2,
            "timestamp": self._now(),
            "type": "error" if result.error else "tool_result",
            "provider": agent_id,
            "tool_name": self.name,
            "content": result.content[:2000] if result.content else None,
            "status_code": result.exit_code,
            "error": result.error,
            "duration_ms": duration_ms,
            "metadata": {"integration": "tracea-mcp"},
        }

        # Post both events
        try:
            await event_post_fn([call_event, result_event])
        except Exception:
            pass  # don't fail tool execution if tracea is down

        # Return MCP-format result
        return {
            "content": [
                {
                    "type": "text",
                    "text": result.content if result.success else f"Error: {result.error}",
                }
            ]
        }

    @staticmethod
    def _make_uuid() -> str:
        import uuid
        return str(uuid.uuid4())

    @staticmethod
    def _now() -> str:
        import time
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
