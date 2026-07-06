# tracea plugin for Claude Code

Claude Code supports lifecycle hooks via `.claude/settings.json`. This plugin uses `PreToolUse`, `PostToolUse`, and `Stop` hooks to emit tracea events.

> **Want full LLM I/O (prompts + responses)?** Claude Code ships native OpenTelemetry export. See [`docs/otel-setup.md`](../../docs/otel-setup.md) — it's a few env vars and captures everything. The hooks below remain useful for lightweight tool-call-only tracking.

## Installation

1. Copy `tracea-hook.sh` to a location in your PATH (e.g. `~/.local/bin/`):
   ```bash
   chmod +x tracea-hook.sh
   cp tracea-hook.sh ~/.local/bin/
   ```

2. Add hooks to your Claude Code settings:

   **Global** (`~/.claude/settings.json`):
   ```json
   {
     "hooks": {
       "PreToolUse": "tracea-hook.sh pre",
       "PostToolUse": "tracea-hook.sh post",
       "Stop": "tracea-hook.sh stop"
     }
   }
   ```

   **Project-local** (`.claude/settings.json` in your repo):
   ```json
   {
     "hooks": {
       "PreToolUse": ".claude/tracea-hook.sh pre",
       "PostToolUse": ".claude/tracea-hook.sh post",
       "Stop": ".claude/tracea-hook.sh stop"
     }
   }
   ```

3. Set environment variables (optional):
   ```bash
   export TRACEA_SERVER_URL=http://localhost:8080
   export TRACEA_API_KEY=dev-mode
   export TRACEA_AGENT_ID=claude-code
   export TRACEA_USER_ID=darshan   # must match a user in the web UI
   ```

   Or use `tracea init` (Python SDK) to create `~/.tracea/config.json` once.

## Hook capabilities

| Hook        | Fires when                    | Event emitted |
|-------------|------------------------------|---------------|
| `PreToolUse`| Before every tool invocation | `tool_call`   |
| `PostToolUse`| After every tool invocation | `tool_result` |
| `Stop`      | When Claude Code exits       | `session_end` |

## Limitations (hook-based capture)

The hooks above capture **tool calls only** — not the LLM's conversational input/output. Claude Code's hook API exposes `CLAUDE_TOOL_NAME` and `CLAUDE_TOOL_INPUT` env vars but not the user's prompt or the model's response text.

**For full LLM I/O capture** (user prompts + assistant responses + token usage + cost), use Claude Code's native OpenTelemetry export instead of (or alongside) these hooks. See [`docs/otel-setup.md`](../../docs/otel-setup.md) for setup.

Other notes:
- Tool results are not exposed in hook env vars (only `CLAUDE_TOOL_INPUT`). Use the OTLP path for full tool I/O.
- Requires `curl` and `jq` to be installed.
