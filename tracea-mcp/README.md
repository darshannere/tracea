# tracea-mcp

MCP server for tracea agent observability. Logs tool calls from Claude Code and OpenClaw agents to your self-hosted tracea server.

## Installation

```bash
pip install tracea-mcp
# or
uvx tracea-mcp
```

## Usage

### Claude Code

```bash
claude mcp add tracea -- uvx tracea-mcp --api-key YOUR_API_KEY --server-url http://localhost:8000
```

### OpenClaw

Same approach — OpenClaw uses the standard MCP stdio protocol.

## What it captures

- Every tool call (Bash, Read, Write, Edit, Glob, Grep)
- Tool execution duration and output
- Full execution sequence per session
- Errors and exit codes

## Environment Variables

- `TRACEA_API_KEY` — your tracea server API key
- `TRACEA_SERVER_URL` — tracea server URL (default: http://localhost:8000)
- `TRACEA_AGENT_ID` — agent identifier (default: claude-code)
