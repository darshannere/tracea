"""Write tool handler."""
import os
from tracea_mcp.tools.base import BaseTool, ToolResult


class WriteTool(BaseTool):
    """Writes content to a file."""

    @property
    def name(self) -> str:
        return "Write"

    @property
    def description(self) -> str:
        return "Write content to a file (creates or overwrites)"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
            },
            "required": ["file_path", "content"],
        }

    async def execute(self, args: dict) -> ToolResult:
        file_path = os.path.realpath(os.path.expanduser(args["file_path"]))
        content = args["content"]

        try:
            os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return ToolResult(
                success=True,
                content=f"Written {len(content)} bytes to {file_path}",
                exit_code=0,
            )
        except Exception as e:
            return ToolResult(success=False, content="", error=str(e), exit_code=1)
