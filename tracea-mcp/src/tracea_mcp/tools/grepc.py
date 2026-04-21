"""Grep tool handler."""
import os
import re
from tracea_mcp.tools.base import BaseTool, ToolResult


class GrepTool(BaseTool):
    """Searches for patterns in files."""

    @property
    def name(self) -> str:
        return "Grep"

    @property
    def description(self) -> str:
        return "Search for a pattern in files (like grep -n)"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for",
                },
                "file_path": {
                    "type": "string",
                    "description": "File or directory to search in",
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Case sensitive search",
                    "default": False,
                },
                "matches_per_file": {
                    "type": "integer",
                    "description": "Max matches per file",
                    "default": 10,
                },
            },
            "required": ["pattern", "file_path"],
        }

    async def execute(self, args: dict) -> ToolResult:
        pattern = args["pattern"]
        file_path = os.path.expanduser(args["file_path"])
        case_sensitive = args.get("case_sensitive", False)
        matches_per_file = args.get("matches_per_file", 10)

        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            compiled = re.compile(pattern, flags)
        except re.error as e:
            return ToolResult(success=False, content="", error=f"Invalid regex: {e}", exit_code=1)

        try:
            results = []
            count = 0

            if os.path.isfile(file_path):
                paths = [file_path]
            else:
                paths = []
                for root, dirs, files in os.walk(file_path):
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    for fname in files:
                        if not fname.startswith("."):
                            paths.append(os.path.join(root, fname))

            for fpath in paths:
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        for lineno, line in enumerate(f, 1):
                            if compiled.search(line):
                                results.append(f"{fpath}:{lineno}:{line.rstrip()}")
                                count += 1
                                if count >= matches_per_file * 10:
                                    break
                except (OSError, UnicodeDecodeError):
                    continue
                if count >= matches_per_file * 10:
                    break

            content = "\n".join(results[:matches_per_file])
            return ToolResult(
                success=True,
                content=f"{count} matches:\n{content}" if results else f"{count} matches",
                exit_code=0,
            )
        except Exception as e:
            return ToolResult(success=False, content="", error=str(e), exit_code=1)
