# tracea-mcp

MCP (Model Context Protocol) server for tracea agent observability. Exposes tracea logging tools to agents that support MCP.

## What it does

tracea-mcp adds a `log_to_tracea` tool to your agent. When the agent invokes it, the event is sent to your self-hosted tracea server. This works with any MCP-compatible agent (Kimi, Cursor, Cline, Zed, Claude Code with MCP, etc.).

**Note:** MCP is an *additive* integration — the agent must explicitly call `log_to_tracea`. For automatic interception of all tool calls, use the [native hook plugins](../tracea-plugins/) instead (Claude Code, Gemini CLI, OpenCode).

## Installation

```bash
pip install tracea-mcp
```

Or run without installing:

```bash
uvx tracea-mcp --api-key YOUR_KEY --server-url http://localhost:8080
```

## CLI Options

| Option | Env Var | Default | Description |
|--------|---------|---------|-------------|
| `--api-key` | `TRACEA_API_KEY` | — | Required. Your tracea API key. |
| `--server-url` | `TRACEA_SERVER_URL` | `http://localhost:8080` | tracea server URL. |
| `--agent-id` | `TRACEA_AGENT_ID` | `claude-code` | Agent identifier for events. |

## Agent Setup

### Kimi CLI

Add to `~/.kimi/mcp.json`:

```json
{
  "mcpServers": {
    "tracea": {
      "command": "uvx",
      "args": [
        "tracea-mcp",
        "--api-key", "YOUR_API_KEY",
        "--server-url", "http://localhost:8080",
        "--agent-id", "kimi"
      ]
    }
  }
}
```

### Cursor

Go to **Settings → MCP → Add Server**:

- Name: `tracea`
- Command: `uvx tracea-mcp --api-key YOUR_API_KEY --server-url http://localhost:8080 --agent-id cursor`

Or edit `~/.cursor/mcp.json` directly.

### Cline

Add to Cline's MCP settings (varies by IDE):

```json
{
  "mcpServers": {
    "tracea": {
      "command": "uvx",
      "args": [
        "tracea-mcp",
        "--api-key", "YOUR_API_KEY",
        "--server-url", "http://localhost:8080",
        "--agent-id", "cline"
      ]
    }
  }
}
```

### Zed

Add to Zed's `settings.json`:

```json
{
  "context_servers": {
    "tracea": {
      "command": "uvx",
      "args": ["tracea-mcp", "--api-key", "YOUR_API_KEY", "--server-url", "http://localhost:8080", "--agent-id", "zed"]
    }
  }
}
```

### Claude Code (MCP mode)

```bash
claude mcp add tracea -- uvx tracea-mcp --api-key YOUR_API_KEY --server-url http://localhost:8080
```

**Note:** For Claude Code, the [native hook plugin](../tracea-plugins/claude-code/) is recommended instead — it intercepts all tool calls automatically without requiring the agent to explicitly invoke tracea.

## What it captures

The MCP server exposes a single tool: `log_to_tracea`. The agent calls it with:

- `event_type` — e.g. `tool_call`, `tool_result`, `session_start`
- `content` — JSON content of the event
- `metadata` — optional key-value metadata

Events are POSTed to `/api/v1/events/mcp` on your tracea server.

## Development

```bash
cd tracea-mcp
pip install -e ".[dev]"
pytest
```
