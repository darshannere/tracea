# tracea plugin for OpenCode

OpenCode supports a TypeScript plugin system via `.opencode/plugins/*.ts`. This plugin uses `tool.execute.before`, `tool.execute.after`, and `session.end` hooks to emit tracea events.

## Installation

1. Copy `tracea-plugin.ts` to your OpenCode plugins directory:
   ```bash
   mkdir -p ~/.opencode/plugins
   cp tracea-plugin.ts ~/.opencode/plugins/
   ```

   Or use the project-local plugins directory:
   ```bash
   mkdir -p .opencode/plugins
   cp tracea-plugin.ts .opencode/plugins/
   ```

2. OpenCode will auto-discover and load the plugin on startup.

3. Set environment variables (optional):
   ```bash
   export TRACEA_SERVER_URL=http://localhost:8080
   export TRACEA_API_KEY=dev-mode
   export TRACEA_AGENT_ID=opencode
   ```

## Hook capabilities

| Hook                  | Fires when                    | Event emitted |
|-----------------------|------------------------------|---------------|
| `tool.execute.before`| Before every tool invocation | `tool_call`   |
| `tool.execute.after` | After every tool invocation  | `tool_result` |
| `session.end`        | When the session ends        | `session_end` |
| `onLoad`             | When the plugin loads        | `session_start` |

## Features

- **Auto-timed tool calls**: `tool.execute.before` records start time in `ctx.state`; `tool.execute.after` computes elapsed duration.
- **Tool correlation**: `tool_call_id` is passed through `ctx.state` to link call and result events.
- **Error capture**: Tool errors are captured and sent as the `error` field on `tool_result`.
- **Fire-and-forget**: Uses `fetch` with a try/catch — never blocks or crashes the agent.

## TypeScript types

The plugin references `opencode` types (`Plugin`, `HookContext`). OpenCode's plugin runtime provides these types at load time. No npm install is required.
