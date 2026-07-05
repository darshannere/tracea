# OTLP Setup — Capturing Full LLM I/O from Coding Agents

tracea accepts **OpenTelemetry (OTLP/HTTP)** export from coding agents that emit it natively. This captures the full conversation — user prompts, assistant responses, tool calls, token usage, and cost — with **zero instrumentation**.

This is the recommended path for agents that support it. Agents without native OTel (OpenCode, Kimi CLI) use the plugin-hook path instead (see [`tracea-plugins/`](../tracea-plugins/)).

---

## Supported agents

| Agent | Native OTel? | Captures | Setup |
|---|---|---|---|
| **Claude Code** | ✅ | Full LLM I/O + tool calls + spans + metrics | env vars |
| **Gemini CLI** | ✅ | Full LLM I/O + metrics | `.gemini/settings.json` |
| OpenCode | ❌ | tool calls only (plugin) | [`tracea-plugins/opencode/`](../tracea-plugins/opencode/) |
| Kimi CLI | ❌ | tool calls only (plugin) | [`tracea-plugins/kimi/`](../tracea-plugins/kimi/) |

---

## Claude Code

### 1. Point Claude Code at tracea and turn on telemetry

Add these to your shell profile (`~/.zshrc`, `~/.bashrc`) or your project's `.env`:

```bash
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:8080

# Capture full request/response bodies (inline, ≤60KB each):
export OTEL_LOG_RAW_API_BODIES=1

# Or, finer-grained control:
# export OTEL_LOG_USER_PROMPTS=1
# export OTEL_LOG_ASSISTANT_RESPONSES=1
# export OTEL_LOG_TOOL_DETAILS=1
```

### 2. (If tracea runs in api_key mode) pass an API key

```bash
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer%20<your-tracea-api-key>"
```

The OTel SDK URL-encodes the header value — the `%20` is intentional. Generate a key from the tracea dashboard Settings page.

### 3. Verify

Run Claude Code, ask it anything, then check the tracea dashboard. You should see `chat.completion` events with `role=user` and `role=assistant`, populated `content`, token counts, and estimated cost.

### What you get

| OTel signal | tracea storage | Notes |
|---|---|---|
| Logs (`claude_code.api_response_body`, etc.) | `events` table | Mapped to `chat.completion` with role + content |
| Traces (spans) | `spans` table | Tree view (v2 dashboard) |
| Metrics (`claude_code.token.usage`, etc.) | `metrics` table | Aggregates (v2 dashboard) |

### Auth modes

- **`TRACEA_AUTH_MODE=disabled`** or **`TRACEA_DEV_MODE=1`**: no auth needed. Use for local dev.
- **`TRACEA_AUTH_MODE=api_key`**: pass the header above. Required for shared/prod deployments.

### Opting out of content capture

tracea stores whatever OTel sends. If you want tracea to **drop** content even when it arrives:

```bash
export TRACEA_CAPTURE_CONTENT=0
```

This zeros out the `content` field on all OTel-sourced events server-side.

---

## Gemini CLI

### 1. Enable telemetry in `.gemini/settings.json` (project or `~/.gemini/settings.json`):

```json
{
  "telemetry": {
    "enabled": true,
    "target": "local",
    "outfile": ".gemini/telemetry.log"
  },
  "GEMINI_TELEMETRY_OTLP_ENDPOINT": "http://localhost:8080"
}
```

### 2. Or via environment variables:

```bash
export GEMINI_TELEMETRY_ENABLED=true
export GEMINI_TELEMETRY_OTLP_ENDPOINT=http://localhost:8080
export GEMINI_TELEMETRY_LOG_PROMPTS=true
```

### 3. (If tracea runs in api_key mode):

Gemini CLI's OTLP exporter supports the same `OTEL_EXPORTER_OTLP_HEADERS` env var as Claude Code — see above.

### Verify

Run `gemini`, ask a question, check the dashboard. Gemini emits the standard `gen_ai.client.inference.operation.details` event, which tracea flattens into one `chat.completion` event per message (system + user + assistant).

---

## Troubleshooting

### No events appear

1. Confirm the server is listening: `curl http://localhost:8080/health` → `{"status":"ok"}`
2. Confirm OTLP endpoints respond: `curl -X POST http://localhost:8080/v1/logs -H "Content-Type: application/json" -d '{}'` → HTTP 200
3. Check the tracea server logs for parse errors (`Failed to parse OTLP...`)
4. Verify the exporter endpoint URL — it must be the base URL (`http://localhost:8080`), NOT `http://localhost:8080/v1/traces`. The SDK appends `/v1/<signal>`.

### Content is empty

- Claude Code: ensure `OTEL_LOG_RAW_API_BODIES=1` (or the finer-grained `OTEL_LOG_USER_PROMPTS`/`OTEL_LOG_ASSISTANT_RESPONSES`)
- Gemini CLI: ensure `GEMINI_TELEMETRY_LOG_PROMPTS=true`
- tracea: ensure `TRACEA_CAPTURE_CONTENT` is unset or `1` (not `0`)

### 401 Unauthorized

- In `api_key` mode, you must pass `OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer%20<key>"`
- In dev mode (`TRACEA_DEV_MODE=1` or `TRACEA_AUTH_MODE=disabled`), no header is needed

### Bodies truncated at 60KB

This is a v1 limitation. `OTEL_LOG_RAW_API_BODIES` truncates inline bodies to 60KB. Untruncated file-dir fetch is on the v2 roadmap. Long agentic turns may show partial assistant responses.

---

## References

- [Claude Code monitoring docs](https://docs.claude.com/en/docs/claude-code/monitoring-usage)
- [Gemini CLI telemetry docs](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/telemetry.md)
- [OTLP/HTTP spec](https://opentelemetry.io/docs/specs/otlp/)
- [GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai)
