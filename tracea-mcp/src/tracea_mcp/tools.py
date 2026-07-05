"""Tools module for tracea-mcp."""
import json
import os
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from tracea_mcp.client import get_client


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


class BrainTool(BaseTool):
    """Query tracea's Company Brain for relevant knowledge."""

    @property
    def name(self) -> str:
        return "brain"

    @property
    def description(self) -> str:
        return (
            "Query the Company Brain — a synthesized knowledge base built from past "
            "agent sessions. Returns workflows, error fixes, and codebase insights "
            "relevant to your current task. Use this before starting work on a new "
            "task to learn from past agent behavior."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query — keywords or a natural language question",
                },
                "category": {
                    "type": "string",
                    "enum": ["workflow", "error_fix", "codebase"],
                    "description": "Optional filter by category",
                },
            },
            "required": ["query"],
        }

    async def execute(self, args: dict) -> ToolResult:
        query = args.get("query", "")
        category = args.get("category")

        server_url = os.environ.get("TRACEA_SERVER_URL", "http://localhost:8080").rstrip("/")
        api_key = os.environ.get("TRACEA_API_KEY", "")

        params = {"q": query, "limit": "10"}
        if category:
            params["category"] = category

        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{server_url}/api/v1/brain/entries",
                    params=params,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                content="",
                error=f"Brain API returned {e.response.status_code}: {e.response.text[:200]}",
                exit_code=e.response.status_code,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=f"Failed to query brain: {e}",
                exit_code=1,
            )

        entries = data.get("entries", [])
        if not entries:
            return ToolResult(
                success=True,
                content="No relevant knowledge found in the Company Brain.",
            )

        lines = [f"Found {len(entries)} relevant entr{'y' if len(entries) == 1 else 'ies'}:\n"]
        for i, entry in enumerate(entries, 1):
            lines.append(f"{i}. [{entry['category'].replace('_', ' ').title()}] {entry['title']}")
            lines.append(f"   Confidence: {entry['confidence'] * 100:.0f}% | Reinforced: {entry['hit_count']} time{'s' if entry['hit_count'] != 1 else ''}")
            lines.append(f"   {entry['content'][:500]}")
            if len(entry['content']) > 500:
                lines.append("   ...")
            lines.append("")

        return ToolResult(success=True, content="\n".join(lines))


class LogToTraceaTool(BaseTool):
    """Log an event directly to the tracea server."""

    @property
    def name(self) -> str:
        return "log_to_tracea"

    @property
    def description(self) -> str:
        return "Log an event directly to the tracea server."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "event_type": {
                    "type": "string",
                    "description": "Event type (e.g., tool_call, tool_result, session_start, session_end)",
                },
                "content": {
                    "type": "string",
                    "description": "JSON string or text payload of the event",
                },
                "metadata": {
                    "type": "object",
                    "description": "Optional key-value metadata",
                },
            },
            "required": ["event_type", "content"],
        }

    async def execute(self, args: dict) -> ToolResult:
        event_type = args.get("event_type", "")
        content = args.get("content", "")
        metadata = args.get("metadata") or {}

        if not event_type:
            return ToolResult(
                success=False,
                content="",
                error="Missing required argument: event_type",
                exit_code=400,
            )

        if isinstance(content, (dict, list)):
            content_str = json.dumps(content, ensure_ascii=False)
        else:
            content_str = str(content)

        from tracea_mcp.session import get_current_session, next_sequence_for

        session = get_current_session()
        if session:
            session_id = session.session_id
            agent_id = session.agent_id
            sequence = next_sequence_for(session_id)
        else:
            session_id = os.environ.get("TRACEA_SESSION_ID") or str(uuid.uuid4())
            agent_id = os.environ.get("TRACEA_AGENT_ID", "claude-code")
            sequence = 1

        user_id = os.environ.get("TRACEA_USER_ID", "")

        event = {
            "event_id": str(uuid.uuid4()),
            "session_id": session_id,
            "agent_id": agent_id,
            "user_id": user_id,
            "sequence": sequence,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "type": event_type,
            "provider": agent_id,
            "content": content_str,
            "metadata": {**metadata, "integration": "tracea-mcp"},
        }

        # If tool_name is present in metadata, elevate it to the top-level
        if "tool_name" in metadata:
            event["tool_name"] = metadata["tool_name"]
        if "duration_ms" in metadata:
            try:
                event["duration_ms"] = int(metadata["duration_ms"])
            except (ValueError, TypeError):
                pass
        if "status_code" in metadata:
            try:
                event["status_code"] = int(metadata["status_code"])
            except (ValueError, TypeError):
                pass
        if "error" in metadata:
            event["error"] = str(metadata["error"])

        try:
            client = get_client()
            accepted = await client.post_events([event])
            return ToolResult(
                success=True,
                content=f"Successfully logged event to tracea. Accepted: {accepted}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=f"Failed to post event to tracea: {e}",
                exit_code=500,
            )


class ToolRegistry:
    """Registry of all MCP tools exposed by tracea-mcp."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._register_defaults()

    def _register_defaults(self):
        for tool in [
            BrainTool(),
            LogToTraceaTool(),
        ]:
            self._tools[tool.name] = tool

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[dict]:
        """Return list of tool definitions for MCP tools/list response."""
        tools = []
        for tool in self._tools.values():
            tools.append({
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
            })
        return tools
