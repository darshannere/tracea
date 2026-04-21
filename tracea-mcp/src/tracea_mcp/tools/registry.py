"""Tool registry for tracea-mcp."""
from tracea_mcp.tools.base import BaseTool
from tracea_mcp.tools.bash import BashTool
from tracea_mcp.tools.read import ReadTool
from tracea_mcp.tools.write import WriteTool
from tracea_mcp.tools.edit import EditTool
from tracea_mcp.tools.glob import GlobTool
from tracea_mcp.tools.grepc import GrepTool


class ToolRegistry:
    """Registry of all MCP tools exposed by tracea-mcp."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._register_defaults()

    def _register_defaults(self):
        for tool in [
            BashTool(),
            ReadTool(),
            WriteTool(),
            EditTool(),
            GlobTool(),
            GrepTool(),
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
