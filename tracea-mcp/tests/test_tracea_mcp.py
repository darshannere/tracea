"""Integration tests for tracea-mcp server.

Tests the full MCP handshake by spawning the server as a subprocess,
sending JSON-RPC commands over stdin, and verifying responses and events.
"""
import asyncio
import json
import os
import select
import subprocess
import sys
import threading
import time

import pytest

# Source path for tracea_mcp imports
SRC_PATH = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, SRC_PATH)


class MCPClient:
    """Minimal JSON-RPC client over subprocess stdin/stdout."""

    def __init__(self, proc: subprocess.Popen):
        self.proc = proc
        self._msg_id = 0

    def send(self, method: str, params: dict | None = None) -> dict | None:
        """Send a JSON-RPC request with Content-Length framing.
        Returns the response dict, or None for notifications."""
        self._msg_id += 1
        msg = {
            "jsonrpc": "2.0",
            "id": self._msg_id,
            "method": method,
            "params": params or {},
        }
        body = json.dumps(msg, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
        self.proc.stdin.write(header + body)
        self.proc.stdin.flush()
        # Notifications (methods starting with "notifications/") do not receive
        # a response from the server — return None immediately.
        if method.startswith("notifications/"):
            return None
        return self._read_message(timeout=15.0)

    def _read_message(self, timeout: float = 10.0) -> dict:
        """Read a JSON-RPC message with Content-Length framing."""
        import fcntl
        fd = self.proc.stdout.fileno()
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

        deadline = time.monotonic() + timeout
        buf = b""

        while True:
            try:
                chunk = self.proc.stdout.read(4096)
                if chunk:
                    buf += chunk
            except BlockingIOError:
                pass

            # Try to parse a complete message from buffer
            while True:
                header_end = buf.find(b"\r\n\r\n")
                if header_end == -1:
                    break
                header = buf[:header_end].decode("utf-8")
                body_start = header_end + 4
                msg_length = None
                for line in header.split("\r\n"):
                    if line.lower().startswith("content-length:"):
                        try:
                            msg_length = int(line.split(":", 1)[1].strip())
                        except ValueError:
                            pass
                        break
                if msg_length is None:
                    raise ValueError("Missing Content-Length header")
                if len(buf) < body_start + msg_length:
                    break
                body = buf[body_start:body_start + msg_length]
                buf = buf[body_start + msg_length:]
                return json.loads(body.decode("utf-8"))

            if time.monotonic() > deadline:
                raise TimeoutError(f"No response after {timeout}s")
            time.sleep(0.05)


class EventCapture:
    def __init__(self):
        self.events: list[dict] = []


class _CaptureServer:
    """Lightweight async HTTP server that captures events posted by tracea-mcp."""

    def __init__(self, capture: EventCapture):
        self.capture = capture
        self._server: asyncio.Server | None = None
        self._stop_event: threading.Event = threading.Event()
        self.port: int = 0

    async def start(self, host: str = "127.0.0.1", port: int = 8000):
        self.port = port

        async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            try:
                # Read the HTTP request line
                line = await reader.readline()
                if not line or line.startswith(b"GET"):
                    writer.write(b"HTTP/1.1 200 OK\r\n\r\n")
                    await writer.drain()
                    return

                # Read headers
                headers = {}
                while True:
                    hline = await reader.readline()
                    if hline in (b"", b"\r\n"):
                        break
                    if b":" in hline:
                        k, v = hline.decode().split(":", 1)
                        headers[k.strip()] = v.strip()

                # Read body
                content_length = int(headers.get("Content-Length", 0))
                body = await reader.read(content_length) if content_length else b""

                # Parse JSON and capture events
                if b"api/v1/events/mcp" in line:
                    try:
                        payload = json.loads(body.decode("utf-8"))
                        self.capture.events.extend(payload.get("events", []))
                    except Exception:
                        pass

                # Always return 200
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 21\r\n\r\n{\"accepted\":1}")
                await writer.drain()
            except Exception:
                pass
            finally:
                writer.close()
                await writer.wait_closed()

        self._server = await asyncio.start_server(handler, host, port)
        if self._server.sockets:
            self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()


async def _run_and_notify(
    server: _CaptureServer,
    ready_event: threading.Event,
    port_holder: list[int],
):
    await server.start("127.0.0.1", 0)
    port_holder[0] = server.port
    ready_event.set()
    while not server._stop_event.is_set():
        await asyncio.sleep(0.25)
    await server.stop()


@pytest.fixture
def mock_tracea_server():
    capture = EventCapture()
    server = _CaptureServer(capture)
    ready_event = threading.Event()
    bound_port_holder: list[int] = [0]

    def run_server():
        asyncio.run(_run_and_notify(server, ready_event, bound_port_holder))

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    ready_event.wait(timeout=5)

    yield capture, bound_port_holder[0]

    server._stop_event.set()
    server_thread.join(timeout=3)


@pytest.fixture
def mcp_server(mock_tracea_server):
    capture, port = mock_tracea_server
    env = {
        **os.environ,
        "TRACEA_API_KEY": "test-key",
        "TRACEA_SERVER_URL": f"http://127.0.0.1:{port}",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "tracea_mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        env=env,
    )
    proc._event_capture = capture
    yield proc

    # Drain stderr before terminating
    stderr_chunks = []
    while True:
        ready, _, _ = select.select([proc.stderr], [], [], 0.5)
        if ready:
            chunk = proc.stderr.read(4096)
            if chunk:
                stderr_chunks.append(chunk.decode("utf-8", errors="replace"))
            else:
                break
        else:
            break

    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def test_full_mcp_handshake(mcp_server):
    client = MCPClient(mcp_server)

    # 1. Initialize
    init_resp = client.send("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "1.0"},
    })
    assert init_resp["result"]["protocolVersion"] == "2024-11-05"
    assert init_resp["result"]["serverInfo"]["name"] == "tracea-mcp"
    assert init_resp["result"]["serverInfo"]["version"] == "0.1.0"
    assert init_resp["result"]["capabilities"]["tools"] == {"listChanged": False}

    # 2. Client ready notification
    client.send("notifications/initialized", {})

    # 3. List tools
    tools_resp = client.send("tools/list")
    tool_names = [t["name"] for t in tools_resp["result"]["tools"]]
    assert set(tool_names) == {"Bash", "Read", "Write", "Edit", "Glob", "Grep"}

    # 4. Execute Read tool (use /etc/hosts which exists on all Unix systems)
    read_resp = client.send("tools/call", {
        "name": "Read",
        "arguments": {"file_path": "/etc/hosts"},
    })
    content_text = read_resp["result"]["content"][0]["text"]
    assert content_text.strip(), "Read tool should return non-empty content for /etc/hosts"

    # 5. Shutdown
    shutdown_resp = client.send("shutdown", {})
    assert shutdown_resp["result"] is None

    mcp_server.wait(timeout=5)
    stderr = mcp_server.stderr.read().decode("utf-8", errors="replace").strip()
    assert "Traceback" not in stderr, f"Server crashed with traceback:\n{stderr}"


def test_events_emitted_to_tracea(mcp_server):
    client = MCPClient(mcp_server)

    client.send("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "1.0"},
    })
    client.send("notifications/initialized", {})

    client.send("tools/call", {
        "name": "Read",
        "arguments": {"file_path": "/etc/hosts"},
    })

    client.send("shutdown", {})
    mcp_server.wait(timeout=5)

    captured = mcp_server._event_capture.events
    event_types = [e["type"] for e in captured]

    for expected in ("session_start", "tool_call", "tool_result", "session_end"):
        assert expected in event_types, f"Missing {expected} event. Got: {event_types}"

    session_start = next(e for e in captured if e["type"] == "session_start")
    assert session_start["provider"] in ("claude-code", "openclaw")
    assert session_start["session_id"]
    assert session_start["sequence"] > 0
    assert session_start["timestamp"].endswith("Z")
    assert session_start["metadata"]["integration"] == "tracea-mcp"

    tool_call = next(e for e in captured if e["type"] == "tool_call")
    assert tool_call["tool_name"] == "Read"
    assert tool_call["provider"] in ("claude-code", "openclaw")
    assert tool_call["session_id"] == session_start["session_id"]
    assert tool_call["sequence"] > 0
    assert tool_call["timestamp"].endswith("Z")
    args = json.loads(tool_call["content"])
    assert args["file_path"] == "/etc/hosts"

    tool_result = next(e for e in captured if e["type"] == "tool_result")
    assert tool_result["tool_name"] == "Read"
    assert tool_result["status_code"] == 0, f"Expected exit 0, got: {tool_result['status_code']}"
    assert tool_result["content"] is not None
    assert tool_result["duration_ms"] >= 0
    assert tool_result["session_id"] == session_start["session_id"]

    session_end = next(e for e in captured if e["type"] == "session_end")
    assert session_end["session_id"] == session_start["session_id"]
    assert session_end["provider"] in ("claude-code", "openclaw")
    assert session_end["timestamp"].endswith("Z")