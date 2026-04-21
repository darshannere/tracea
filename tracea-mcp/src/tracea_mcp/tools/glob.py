"""Glob tool handler."""
import fnmatch
import os
from tracea_mcp.tools.base import BaseTool, ToolResult


class GlobTool(BaseTool):
    """Finds files matching a glob pattern."""

    @property
    def name(self) -> str:
        return "Glob"

    @property
    def description(self) -> str:
        return "Find files matching a glob pattern"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g. **/*.py)",
                },
                "base_dir": {
                    "type": "string",
                    "description": "Directory to search in (default: current directory)",
                    "default": ".",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, args: dict) -> ToolResult:
        pattern = args["pattern"]
        base_dir = os.path.expanduser(args.get("base_dir", "."))

        try:
            matches = []
            for root, dirs, files in os.walk(base_dir, followlinks=False):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for fname in files:
                    if fnmatch.fnmatch(fname, pattern) or fnmatch.fnmatch(os.path.join(root, fname), pattern):
                        matches.append(os.path.join(root, fname))
            content = "\n".join(matches[:200])
            count = len(matches)
            return ToolResult(
                success=True,
                content=f"{count} matches:\n{content}" if matches else f"{count} matches",
                exit_code=0,
            )
        except Exception as e:
            return ToolResult(success=False, content="", error=str(e), exit_code=1)
