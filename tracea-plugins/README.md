# tracea-plugins — Agent-specific observability hooks

This directory contains agent-specific plugins that intercept tool calls and
emit events to the tracea server. They complement the `tracea-mcp` integration
(for agents that support MCP) by providing **native lifecycle hooks** for agents
that support interception but not MCP.

## Supported agents

| Agent        | Hook mechanism              | Status | Directory         |
|--------------|----------------------------|--------|-------------------|
| Claude Code  | `.claude/settings.json` hooks | ✅     | `claude-code/`    |
| Gemini CLI   | `settings.json` hooks       | ✅     | `gemini/`         |
| OpenCode     | `.opencode/plugins/*.ts`    | ✅     | `opencode/`       |
| Cursor       | No hooks, only additive MCP | ❌     | Use tracea-mcp    |
| Cline        | No hooks, only additive MCP | ❌     | Use tracea-mcp    |
| Zed          | No hooks, only additive MCP | ❌     | Use tracea-mcp    |
| Kimi CLI     | Native hooks (`PreToolUse`/`PostToolUse`) | ✅     | `kimi/`           |

## Quick start

Each plugin directory contains:
- `README.md` — installation and configuration instructions
- Hook script(s) — the actual interception code

### Environment variables (all plugins)

| Variable            | Default                  | Description        |
|---------------------|--------------------------|--------------------|
| `TRACEA_SERVER_URL` | `http://localhost:8080`  | tracea server URL  |
| `TRACEA_API_KEY`    | `dev-mode`               | API key            |
| `TRACEA_AGENT_ID`   | Agent-specific default   | Agent identifier   |

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Agent CLI  │────▶│ tracea hook  │────▶│ tracea API  │
│  (Claude,   │     │  (shell/TS)  │     │ /api/v1/    │
│  Gemini,    │     │              │     │ events/mcp  │
│  OpenCode)  │     │ Intercepts   │     │             │
└─────────────┘     │ tool calls   │     └─────────────┘
                    └──────────────┘
```

## Events emitted

All plugins emit the same event types:

| Event type      | When emitted                        |
|-----------------|-------------------------------------|
| `session_start` | When a new agent session begins     |
| `tool_call`     | Before a tool is invoked            |
| `tool_result`   | After a tool completes (or errors)  |
| `session_end`   | When the agent session ends         |

## MCP vs. Native hooks

- **tracea-mcp**: Best for agents with full MCP support (Kimi, Cursor, Cline).
  Adds tracea as a tool the agent can call. Limited to explicit tool calls.
- **tracea-plugins**: Best for agents with native hook support (Claude Code,
  Gemini CLI, OpenCode). Intercepts ALL tool calls automatically without
  requiring the agent to explicitly invoke tracea.

## SDK auto-instrumentation (Python)

For Python-based agents, use the `tracea` SDK's auto-instrumentation instead:

```python
import tracea
tracea.init(api_key="dev-mode")

# All httpx LLM calls are automatically captured
tracea.log_tool_call("search", {"query": "python"})
tracea.log_tool_result("search", result={"hits": [...]})
```

See `sdk-python/` in the repo root.
