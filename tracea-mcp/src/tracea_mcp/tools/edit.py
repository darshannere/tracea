"""Edit tool handler."""
import os
import re
from tracea_mcp.tools.base import BaseTool, ToolResult


class EditTool(BaseTool):
    """Applies edits to a file using old_string/new_string replacement."""

    @property
    def name(self) -> str:
        return "Edit"

    @property
    def description(self) -> str:
        return "Apply an edit to a file by replacing old_string with new_string"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to edit",
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact string to replace",
                },
                "new_string": {
                    "type": "string",
                    "description": "The replacement string",
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        }

    async def execute(self, args: dict) -> ToolResult:
        file_path = os.path.expanduser(args["file_path"])
        old_string = args["old_string"]
        new_string = args["new_string"]

        try:
            if not os.path.exists(file_path):
                return ToolResult(success=False, content="", error=f"File not found: {file_path}", exit_code=1)

            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            if old_string not in content:
                return ToolResult(
                    success=False,
                    content="",
                    error=f"old_string not found in file: {repr(old_string[:50])}",
                    exit_code=1,
                )

            new_content = content.replace(old_string, new_string, 1)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return ToolResult(
                success=True,
                content=f"Applied edit to {file_path}",
                exit_code=0,
            )
        except Exception as e:
            return ToolResult(success=False, content="", error=str(e), exit_code=1)
