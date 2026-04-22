# OpenClaw Plugin for tracea

Observability plugin for [OpenClaw](https://github.com/openclaw/openclaw) — the persistent AI agent gateway. This captures the full agent lifecycle beyond simple session-scoped CLI copilots.

## What it captures

| Hook | Event type | Description |
|------|-----------|-------------|
| `before_agent_start` → `agent_end` | `agent_turn` | Full agent reasoning/action cycle with duration |
| `before_tool_call` → `after_tool_call` | `tool_call` / `tool_result` | Individual tool invocations |
| `message_received` | `chat.completion` | Inbound user messages |
| `heartbeat:before` → `heartbeat:after` | `heartbeat` | Periodic agent health checks |
| `before_compaction` → `after_compaction` | `memory_compaction` | Context window compaction events |
| `gateway_start` / `gateway_stop` | `gateway_event` | Gateway lifecycle |
| `session_start` / `session_end` | `session_start` / `session_end` | Session boundaries |

## Installation

1. Copy this directory to your OpenClaw plugins path:

```bash
cp -r tracea-plugins/openclaw /path/to/your/openclaw-plugins/
```

2. Add to `openclaw.json`:

```json
{
  "plugins": {
    "load": {
      "paths": ["/path/to/your/openclaw-plugins/openclaw"]
    },
    "entries": {
      "tracea": {
        "enabled": true
      }
    }
  }
}
```

3. Set environment variables:

```bash
export TRACEA_SERVER_URL="http://localhost:8080"
export TRACEA_API_KEY="your-api-key"
export TRACEA_AGENT_ID="openclaw"
```

4. Clear the jiti cache and restart:

```bash
rm -rf /tmp/jiti
systemctl --user restart openclaw-gateway
```

## Verification

Check gateway logs for the registration message:

```
[tracea] OpenClaw plugin registered — 15 hooks active
```

Send a message to your agent and check the tracea dashboard — you should see:
- A new session with `provider: openclaw`
- `agent_turn` events showing turn duration
- `tool_call` / `tool_result` pairs for each tool invocation

## Architecture

```
OpenClaw Gateway
  │
  ├── before_agent_start ──┐
  ├── before_tool_call  ───┤
  ├── message_received  ───┤──▶ tracea-plugin.ts ──▶ tracea API
  ├── heartbeat:after   ───┤        (15 hooks)
  ├── after_compaction  ───┤
  └── agent_end ───────────┘
```

## Compared to other OpenClaw observability options

| Feature | tracea | openclaw-logfire | openclaw-langsmith |
|--------|--------|-----------------|-------------------|
| Self-hosted | ✅ | ❌ (SaaS) | ❌ (SaaS) |
| Real-time dashboard | ✅ | ✅ | ✅ |
| Detection rules | ✅ | ❌ | ❌ |
| Alert routing | ✅ | ❌ | ❌ |
| AI-powered RCA | ✅ | ❌ | ❌ |
| OTel native | ❌ | ✅ | ✅ |
| Cost | Free | Paid | Paid |

Use tracea when you want **self-hosted observability with detection, alerts, and root-cause analysis**. Use logfire/langsmith when you need OTel-native traces in a managed SaaS.
