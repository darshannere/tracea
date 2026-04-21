"""Read tool handler."""
import itertools
import os
import stat
from tracea_mcp.tools.base import BaseTool, ToolResult


class ReadTool(BaseTool):
    """Reads file contents."""

    @property
    def name(self) -> str:
        return "Read"

    @property
    def description(self) -> str:
        return "Read the contents of a file"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to read",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line offset to start reading from (0-based)",
                    "default": 0,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read",
                },
            },
            "required": ["file_path"],
        }

    async def execute(self, args: dict) -> ToolResult:
        file_path = os.path.realpath(os.path.expanduser(args["file_path"]))
        offset = args.get("offset", 0)
        limit = args.get("limit")

        try:
            if not os.path.exists(file_path):
                return ToolResult(success=False, content="", error=f"File not found: {file_path}", exit_code=1)

            # Check for special files
            st = os.stat(file_path)
            mode = st.st_mode
            if stat.S_ISDIR(mode):
                return ToolResult(success=False, content="", error=f"Cannot read a directory: {file_path}", exit_code=1)
            if stat.S_ISFIFO(mode):
                return ToolResult(success=False, content="", error=f"Cannot read a named pipe (FIFO): {file_path}", exit_code=1)
            if stat.S_ISCHR(mode):
                return ToolResult(success=False, content="", error=f"Cannot read a character device: {file_path}", exit_code=1)

            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = itertools.islice(f, offset, limit + offset if limit else None)
                content = "".join(lines)
            return ToolResult(success=True, content=content, exit_code=0)
        except Exception as e:
            return ToolResult(success=False, content="", error=str(e), exit_code=1)
