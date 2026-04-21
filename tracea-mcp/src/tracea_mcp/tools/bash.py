"""Bash tool handler."""
import asyncio
import os
import shutil
from tracea_mcp.tools.base import BaseTool, ToolResult


class BashTool(BaseTool):
    """Executes bash commands."""

    @property
    def name(self) -> str:
        return "Bash"

    @property
    def description(self) -> str:
        return "Execute a bash command and return its output"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute",
                },
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds (default: 60)",
                    "default": 60,
                },
                "workingDirectory": {
                    "type": "string",
                    "description": "Working directory for the command",
                },
            },
            "required": ["command"],
        }

    async def execute(self, args: dict) -> ToolResult:
        command = args["command"]
        timeout = args.get("timeout", 60)
        cwd = args.get("workingDirectory") or os.getcwd()

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=cwd,
                env={**os.environ, "TERM": "xterm-256color"},
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                output = stdout.decode("utf-8", errors="replace")
                return ToolResult(
                    success=proc.returncode == 0,
                    content=output,
                    error=None if proc.returncode == 0 else f"exit {proc.returncode}",
                    exit_code=proc.returncode or 0,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return ToolResult(
                    success=False,
                    content="",
                    error=f"Command timed out after {timeout}s",
                    exit_code=124,
                )
        except Exception as e:
            return ToolResult(success=False, content="", error=str(e), exit_code=1)
