# tracea plugin for Kimi CLI

Kimi CLI supports lifecycle hooks via `~/.kimi/config.toml`. This plugin uses `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `SessionStart`, and `SessionEnd` hooks to emit tracea events.

## Installation

1. Copy the hook script to a location in your PATH:
   ```bash
   chmod +x tracea-plugins/kimi/tracea-hook.py
   cp tracea-plugins/kimi/tracea-hook.py ~/.kimi/hooks/
   ```

2. Add hooks to `~/.kimi/config.toml`:
   ```toml
   [[hooks]]
   event = "PreToolUse"
   command = "python3 ~/.kimi/hooks/tracea-hook.py pre"

   [[hooks]]
   event = "PostToolUse"
   command = "python3 ~/.kimi/hooks/tracea-hook.py post"

   [[hooks]]
   event = "PostToolUseFailure"
   command = "python3 ~/.kimi/hooks/tracea-hook.py post_failure"

   [[hooks]]
   event = "SessionStart"
   command = "python3 ~/.kimi/hooks/tracea-hook.py session_start"

   [[hooks]]
   event = "SessionEnd"
   command = "python3 ~/.kimi/hooks/tracea-hook.py session_end"
   ```

3. Set environment variables (optional):
   ```bash
   export TRACEA_SERVER_URL=http://localhost:8080
   export TRACEA_API_KEY=dev-mode
   export TRACEA_AGENT_ID=kimi
   ```

## Hook capabilities

| Hook | Fires when | Event emitted |
|------|-----------|---------------|
| `PreToolUse` | Before every tool invocation | `tool_call` |
| `PostToolUse` | After successful tool execution | `tool_result` |
| `PostToolUseFailure` | After failed tool execution | `tool_result` (with error) |
| `SessionStart` | When a session begins | `session_start` |
| `SessionEnd` | When a session ends | `session_end` |

## Communication protocol

Kimi CLI sends JSON context to hooks via stdin. The hook reads this JSON, extracts fields (`tool_name`, `tool_input`, `tool_output`, `error`, `session_id`), and POSTs a tracea event.

## Correlating pre/post calls

Since Kimi runs `PreToolUse` and `PostToolUse` as separate subprocesses, the hook uses a temp file (`/tmp/tracea-kimi-last-tcid`) to pass the `tool_call_id` from pre to post. This works because Kimi executes them sequentially.

## Comparison with MCP

Kimi also supports MCP servers (including `tracea-mcp`). However, **native hooks are strictly better** because:

- **Hooks**: Intercept ALL tool calls automatically — zero agent involvement
- **MCP**: The agent must explicitly choose to use tracea-mcp's wrapped tools

If you previously added `tracea-mcp` to `~/.kimi/mcp.json`, you can remove it once hooks are configured.
