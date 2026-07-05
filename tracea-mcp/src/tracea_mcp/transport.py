"""MCP stdio transport — reads JSON-RPC requests from stdin, writes responses to stdout.

Uses Content-Length framing per the MCP specification:
  Content-Length: <N>\r\n\r\n<JSON body>
"""
import json
import sys
from typing import Any, Optional


class StdioTransport:
    """MCP stdio transport — JSON-RPC over stdin/stdout with Content-Length framing."""

    def __init__(self):
        self._read_buf = b""

    def read_message(self) -> Optional[dict]:
        """Read a single JSON-RPC message from stdin using Content-Length framing."""
        while True:
            # Try to find a complete message in the buffer
            if self._read_buf:
                header_end = self._read_buf.find(b"\r\n\r\n")
                if header_end != -1:
                    header = self._read_buf[:header_end].decode("utf-8", errors="replace")
                    body_start = header_end + 4

                    # Parse Content-Length
                    length = None
                    for line in header.split("\r\n"):
                        if line.lower().startswith("content-length:"):
                            try:
                                length = int(line.split(":", 1)[1].strip())
                            except ValueError:
                                pass
                            break

                    if length is not None and len(self._read_buf) >= body_start + length:
                        body = self._read_buf[body_start:body_start + length]
                        self._read_buf = self._read_buf[body_start + length:]
                        try:
                            return json.loads(body.decode("utf-8"))
                        except json.JSONDecodeError:
                            # Corrupted message — drop it and continue
                            continue

            # Need more data — read from binary buffer to avoid text-mode buffering issues
            try:
                chunk = sys.stdin.buffer.read1(4096)
            except AttributeError:
                chunk = sys.stdin.buffer.read(4096)
            if not chunk:
                # EOF
                return None
            self._read_buf += chunk

    def write_message(self, msg: dict):
        """Write a JSON-RPC message to stdout with Content-Length framing."""
        body = json.dumps(msg, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
        sys.stdout.buffer.write(header + body)
        sys.stdout.buffer.flush()

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
