# tracea plugin for Gemini CLI

Gemini CLI supports lifecycle hooks via `settings.json`. This plugin uses `BeforeTool`, `AfterTool`, `SessionStart`, and `SessionEnd` hooks to emit tracea events.

## Installation

1. Copy `tracea-hook.py` to a location in your PATH (e.g. `~/.local/bin/`):
   ```bash
   chmod +x tracea-hook.py
   cp tracea-hook.py ~/.local/bin/
   ```

2. Add hooks to your Gemini CLI settings:

   **Global** (`~/.gemini/settings.json`):
   ```json
   {
     "hooks": {
       "BeforeTool": ["python3", "tracea-hook.py", "before_tool"],
       "AfterTool": ["python3", "tracea-hook.py", "after_tool"],
       "SessionStart": ["python3", "tracea-hook.py", "session_start"],
       "SessionEnd": ["python3", "tracea-hook.py", "session_end"]
     }
   }
   ```

   **Project-local** (`.gemini/settings.json` in your repo):
   ```json
   {
     "hooks": {
       "BeforeTool": ["python3", ".gemini/tracea-hook.py", "before_tool"],
       "AfterTool": ["python3", ".gemini/tracea-hook.py", "after_tool"],
       "SessionStart": ["python3", ".gemini/tracea-hook.py", "session_start"],
       "SessionEnd": ["python3", ".gemini/tracea-hook.py", "session_end"]
     }
   }
   ```

3. Set environment variables (optional):
   ```bash
   export TRACEA_SERVER_URL=http://localhost:8080
   export TRACEA_API_KEY=dev-mode
   export TRACEA_AGENT_ID=gemini-cli
   ```

## Hook capabilities

| Hook           | Fires when                        | Event emitted |
|----------------|-----------------------------------|---------------|
| `BeforeTool`   | Before every tool invocation      | `tool_call`   |
| `AfterTool`    | After every tool invocation       | `tool_result` |
| `SessionStart` | When a new session begins         | `session_start` |
| `SessionEnd`   | When the session ends             | `session_end` |

## Protocol

Gemini CLI sends JSON payloads to hooks via stdin. The hook reads this JSON,
extracts relevant fields (`tool_name`, `tool_input`, `tool_output`, `error`,
`duration_ms`, `session_id`), and POSTs a tracea event.

## Limitations

- Hook JSON schema may vary by Gemini CLI version. The hook defensively handles missing fields.
- Uses stdlib only (`urllib`) — no external dependencies.
