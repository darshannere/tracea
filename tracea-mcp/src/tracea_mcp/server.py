"""MCP server — main entry point for tracea-mcp."""
import argparse
import asyncio
import os
import signal
import sys
import time
import uuid

from tracea_mcp.transport.stdio import StdioTransport
from tracea_mcp.tools.registry import ToolRegistry
from tracea_mcp.session import create_session, next_sequence_for
from tracea_mcp.client import get_client


class MCPServer:
    """MCP server over stdio transport."""

    def __init__(self, agent_id: str = "claude-code"):
        self.transport = StdioTransport()
        self.registry = ToolRegistry()
        self.agent_id = agent_id
        self.session = create_session(agent_id)
        self.running = True

    async def post_events(self, events: list[dict]):
        """Post events to tracea server."""
        client = get_client()
        try:
            await client.post_events(events)
        except Exception as e:
            print(f"[tracea-mcp] failed to post events: {e}", file=sys.stderr)

    def run(self):
        """Run the MCP server main loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def shutdown():
            self.running = False
            # Emit session_end event
            if not self.session.ended:
                seq = next_sequence_for(self.session.session_id)
                end_event = {
                    "event_id": str(uuid.uuid4()),
                    "session_id": self.session.session_id,
                    "agent_id": self.agent_id,
                    "sequence": seq,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "type": "session_end",
                    "provider": self.agent_id,
                    "metadata": {"integration": "tracea-mcp"},
                }
                try:
                    await self.post_events([end_event])
                except Exception:
                    pass
                self.session.end()
            await get_client().close()

        async def handle_message(msg: dict):
            method = msg.get("method")
            msg_id = msg.get("id")
            params = msg.get("params", {})

            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {"listChanged": False},
                    },
                    "serverInfo": {
                        "name": "tracea-mcp",
                        "version": "0.1.0",
                    },
                }
                self.transport.write_response(msg_id, result)

            elif method == "tools/list":
                tools = self.registry.list_tools()
                self.transport.write_response(msg_id, {"tools": tools})

            elif method == "tools/call":
                name = params.get("name")
                arguments = params.get("arguments", {})
                tool = self.registry.get(name)

                if not tool:
                    self.transport.write_error(msg_id, -32602, f"Unknown tool: {name}")
                    return

                try:
                    result = await tool.log_and_execute(
                        arguments,
                        self.session.session_id,
                        self.agent_id,
                        lambda: next_sequence_for(self.session.session_id),
                        self.post_events,
                    )
                    self.transport.write_response(msg_id, result)
                except Exception as e:
                    self.transport.write_error(msg_id, -32603, f"Tool execution failed: {e}")

            elif method == "notifications/initialized":
                # Client is done initializing — nothing to do
                pass

            elif method == "shutdown":
                self.transport.write_response(msg_id, None)
                self.running = False
                loop.stop()

            else:
                # Unknown method — ignore
                if msg_id:
                    self.transport.write_error(msg_id, -32601, f"Method not found: {method}")

        def signal_handler(sig, frame):
            self.running = False
            loop.quit()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        async def main_loop():
            while self.running:
                msg = self.transport.read_message()
                if msg is None:
                    break
                await handle_message(msg)

            await shutdown()

        try:
            loop.run_until_complete(main_loop())
        finally:
            loop.close()


def main():
    parser = argparse.ArgumentParser(description="tracea-mcp: Agent observability MCP server")
    parser.add_argument("--api-key", help="tracea API key (or set TRACEA_API_KEY env var)")
    parser.add_argument("--server-url", help="tracea server URL (or set TRACEA_SERVER_URL env var)")
    parser.add_argument(
        "--agent-id",
        default=os.environ.get("TRACEA_AGENT_ID", "claude-code"),
        help="Agent identifier (claude-code or openclaw)",
    )
    args = parser.parse_args()

    if args.api_key:
        os.environ["TRACEA_API_KEY"] = args.api_key
    if args.server_url:
        os.environ["TRACEA_SERVER_URL"] = args.server_url

    server = MCPServer(agent_id=args.agent_id)
    server.run()
