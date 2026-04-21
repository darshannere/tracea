"""MCP stdio transport — reads JSON-RPC requests from stdin, writes responses to stdout."""
import json
import sys
from typing import Any, Callable, Optional


class StdioTransport:
    """MCP stdio transport — JSON-RPC over stdin/stdout."""

    def __init__(self):
        self._buf = ""

    def read_message(self) -> Optional[dict]:
        """Read a single JSON-RPC message from stdin.

        MCP uses line-delimited JSON-RPC messages over stdio.
        Reads one line at a time.
        """
        line = sys.stdin.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    def write_message(self, msg: dict):
        """Write a JSON-RPC message to stdout."""
        line = json.dumps(msg, ensure_ascii=False)
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

    def write_response(self, msg_id: Any, result: Any):
        """Write a JSON-RPC response."""
        self.write_message({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": result,
        })

    def write_error(self, msg_id: Any, code: int, message: str):
        """Write a JSON-RPC error response."""
        self.write_message({
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": code,
                "message": message,
            },
        })

    def write_notification(self, method: str, params: dict):
        """Write a JSON-RPC notification (no id)."""
        self.write_message({
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        })
