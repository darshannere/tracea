# tracea plugin for Claude Code

Claude Code supports lifecycle hooks via `.claude/settings.json`. This plugin uses `PreToolUse`, `PostToolUse`, and `Stop` hooks to emit tracea events.

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
   ```

## Hook capabilities

| Hook        | Fires when                    | Event emitted |
|-------------|------------------------------|---------------|
| `PreToolUse`| Before every tool invocation | `tool_call`   |
| `PostToolUse`| After every tool invocation | `tool_result` |
| `Stop`      | When Claude Code exits       | `session_end` |

## Limitations

- Claude Code does **not** expose tool results in hook env vars, only `CLAUDE_TOOL_INPUT`. Result content is limited.
- No `SessionStart` hook exists in Claude Code; sessions are inferred from the first event.
- Requires `curl` and `jq` to be installed.
