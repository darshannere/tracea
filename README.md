# tracea

Self-hosted AI agent observability platform. Trace LLM sessions, detect issues, get AI-powered root cause analysis, and route alerts — all in one place.

## Quick Start

### Option A: Docker (fastest, recommended)

```bash
# Clone and enter the repo
git clone https://github.com/darshannere/tracea.git
cd tracea

# Build and start
docker-compose up --build

# The server starts on http://localhost:8080
# API key is printed in the logs and written to ./data/api_key.txt
# Dashboard: http://localhost:8080/dashboard/
```

### Option B: Local Development

**1. Install dependencies**

```bash
# Backend
pip install -e "."

# Dashboard
cd dashboard && npm install && npm run build && cd ..

# Python SDK (optional)
cd sdk-python && pip install -e "." && cd ..
```

**2. Set up environment**

```bash
cp .env.example .env

# Copy default rules/alerts so the server finds them on first run
mkdir -p data
cp tracea/server/detection/defaults/detection_rules.yaml data/
cp tracea/server/alerts.yaml data/
```

**3. Start the server**

```bash
# Load env vars
export $(grep -v '^#' .env | xargs)

# Start server
uvicorn tracea.server.main:app --host 0.0.0.0 --port 8080 --workers 1
```

The server will:
- Start on `http://localhost:8080`
- Generate an API key on first run (saved to `./data/api_key.txt`)
- Serve the dashboard at `http://localhost:8080/dashboard/`
- Hot-reload detection rules and alerts from `./data/`

**4. Open the dashboard**

Go to `http://localhost:8080/dashboard/` and paste your API key when prompted.

**5. Send your first event**

```bash
API_KEY=$(cat data/api_key.txt)

curl -X POST http://localhost:8080/api/v1/events \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "events": [{
      "event_id": "evt-001",
      "session_id": "sess-001",
      "agent_id": "my-agent",
      "sequence": 1,
      "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
      "type": "chat.completion",
      "provider": "openai",
      "model": "gpt-4o",
      "role": "user",
      "content": "Hello, world!",
      "duration_ms": 120,
      "tokens_used": {"input": 10, "output": 5, "total": 15},
      "cost_usd": 0.0003
    }]
  }'
```

Refresh the dashboard — your session appears in the Sessions view.

---

## Dev Mode (Local Development Only)

For zero-friction local development, enable dev mode to bypass API key authentication:

```bash
TRACEA_DEV_MODE=1 uvicorn tracea.server.main:app --host 0.0.0.0 --port 8080
```

**Never use `TRACEA_DEV_MODE=1` in production.**

---

## Features

- **Session Tracking** — Automatically trace LLM calls, tool executions, errors, and session lifecycle
- **Real-time Dashboard** — React dashboard with insights visualizations: cost trends, token usage, duration distribution, session health, and more
- **Issue Detection** — YAML-configurable detection rules for tool errors, high cost, high latency, rate limits, repeated calls, infinite loops, and more
- **AI-Powered RCA** — Root cause analysis powered by LLMs (OpenAI, Anthropic, or local Ollama)
- **Alert Routing** — Route issues to Slack or generic webhooks with per-destination rate limiting
- **SDK + MCP** — Python SDK with auto-instrumentation, MCP server for agent integration, and native hook plugins for Claude Code / Gemini CLI / OpenCode

---

## Project Structure

```
tracea/
├── tracea/                  # FastAPI backend
│   ├── server/
│   │   ├── main.py         # App entry point
│   │   ├── db.py           # SQLite + WAL
│   │   ├── routes/         # API routes (sessions, issues, config)
│   │   ├── detection/      # Rule engine + watcher
│   │   ├── rca/            # RCA worker + LLM backends
│   │   └── alerts/         # Alert dispatcher
│   └── server/migrations/  # Schema migrations
├── dashboard/              # React 18 + Vite dashboard
│   └── dist/               # Production build (served by FastAPI)
├── sdk-python/             # Python SDK for manual tracing
├── tracea-mcp/             # MCP server for Claude Code integration
├── data/                   # SQLite database + user config (created at runtime)
├── docker-compose.yml      # Docker deployment
└── .env.example            # Env var template
```

---

## Prerequisites

- Python 3.11+
- Node.js 20+ (for dashboard dev)
- SQLite 3.45+ (for WAL mode)

---

## Installation

### 1. Backend

```bash
# Install backend dependencies
pip install -e "."

# Or with uv
uv pip install -e "."
```

### 2. Dashboard

```bash
cd dashboard
npm install

# Development (Vite dev server on port 5173)
npm run dev

# Production build (required for FastAPI to serve it)
npm run build
```

### 3. Python SDK (optional)

```bash
cd sdk-python
pip install -e "."
```

See [sdk-python/README.md](sdk-python/README.md) for usage examples.

### 4. MCP Server (optional)

```bash
cd tracea-mcp
pip install -e "."
```

Or install from PyPI:

```bash
pip install tracea-mcp
# or
uvx tracea-mcp --api-key YOUR_KEY --server-url http://localhost:8080
```

### 5. Agent Plugins (optional)

For agents that support native lifecycle hooks (Claude Code, Gemini CLI, OpenCode), copy the relevant plugin from `tracea-plugins/`:

```bash
# Claude Code — copy hook script
chmod +x tracea-plugins/claude-code/tracea-hook.sh
cp tracea-plugins/claude-code/tracea-hook.sh ~/.local/bin/

# Then add to ~/.claude/settings.json:
# {
#   "hooks": {
#     "PreToolUse": "tracea-hook.sh pre",
#     "PostToolUse": "tracea-hook.sh post",
#     "Stop": "tracea-hook.sh stop"
#   }
# }

# Gemini CLI — copy hook script
chmod +x tracea-plugins/gemini/tracea-hook.py
cp tracea-plugins/gemini/tracea-hook.py ~/.local/bin/

# Then add to ~/.gemini/settings.json:
# {
#   "hooks": {
#     "BeforeTool": ["python3", "tracea-hook.py", "before_tool"],
#     "AfterTool": ["python3", "tracea-hook.py", "after_tool"],
#     "SessionStart": ["python3", "tracea-hook.py", "session_start"],
#     "SessionEnd": ["python3", "tracea-hook.py", "session_end"]
#   }
# }

# OpenCode — copy plugin
cp tracea-plugins/opencode/tracea-plugin.ts ~/.opencode/plugins/
# Auto-discovered on startup
```

See individual plugin READMEs for full details:
- [Claude Code plugin](tracea-plugins/claude-code/README.md)
- [Gemini CLI plugin](tracea-plugins/gemini/README.md)
- [OpenCode plugin](tracea-plugins/opencode/README.md)

---

## Agent Integration Matrix

| Agent | Integration | Auto-captures tool calls | Installation |
|-------|-------------|--------------------------|--------------|
| **Claude Code** | Native hooks (`PreToolUse`/`PostToolUse`) | ✅ All tools | Copy `tracea-hook.sh` + add to `settings.json` |
| **Gemini CLI** | Native hooks (`BeforeTool`/`AfterTool`) | ✅ All tools | Copy `tracea-hook.py` + add to `settings.json` |
| **OpenCode** | Plugin system (`tool.execute.before`) | ✅ All tools | Copy `tracea-plugin.ts` to `~/.opencode/plugins/` |
| **OpenClaw** | Plugin hooks (`api.on()`) | ✅ All tools | Add plugin path to `openclaw.json` |
| **Kimi CLI** | Native hooks (`PreToolUse`/`PostToolUse`/`SessionStart`/`SessionEnd`) | ✅ All tools | Add hooks to `~/.kimi/config.toml` |
| **Cursor** | MCP (additive tools) | ⚠️ Only explicit calls | Add `tracea-mcp` to Cursor MCP settings |
| **Cline** | MCP (additive tools) | ⚠️ Only explicit calls | Add `tracea-mcp` to Cline MCP settings |
| **Zed** | MCP (additive tools) | ⚠️ Only explicit calls | Add `tracea-mcp` to Zed MCP settings |
| **Python scripts** | SDK auto-instrumentation | ✅ All httpx LLM calls + manual logs | `pip install tracea` + `tracea.init()` |

**Native hooks** intercept every tool call automatically. **MCP** adds tracea as a tool the agent can call — the agent decides when to use it.

---

## MCP Configuration

### Kimi CLI

Kimi supports **native hooks** (recommended) or MCP.

**Native hooks** — add to `~/.kimi/config.toml`:
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

See [tracea-plugins/kimi/README.md](tracea-plugins/kimi/README.md) for the hook script.

**MCP** (alternative, not recommended):
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

### Cursor / Cline / Zed

These agents have no native hooks — use MCP:

```bash
uvx tracea-mcp --api-key YOUR_API_KEY --server-url http://localhost:8080 --agent-id cursor
```

---

## Configuration

Copy the example env file and adjust for your setup:

```bash
cp .env.example .env
```

Key variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `TRACEA_DB_PATH` | SQLite database path | `./data/tracea.db` |
| `TRACEA_API_KEY_FILE` | Where to read/write the API key | `./data/api_key.txt` |
| `TRACEA_DATA_DIR` | Directory for user-edited config (rules, alerts) | `./data` |
| `TRACEA_RULES_PATH` | Detection rules YAML path | `./data/detection_rules.yaml` |
| `TRACEA_ALERTS_PATH` | Alerts routing YAML path | `./data/alerts.yaml` |
| `TRACEA_DEV_MODE` | Set to `1` to bypass auth (local dev only) | — |
| `TRACEA_RCA_BACKEND` | RCA LLM backend: `disabled`, `openai`, `anthropic`, `ollama` | `disabled` |
| `TRACEA_RCA_MODEL` | Model to use for RCA | backend default |
| `TRACEA_RCA_BASE_URL` | Custom base URL (for Ollama or proxies) | — |
| `OPENAI_API_KEY` | Required if using OpenAI RCA | — |
| `ANTHROPIC_API_KEY` | Required if using Anthropic RCA | — |

---

## Running

### Backend

```bash
# Load env vars and start server
export $(grep -v '^#' .env | xargs)
uvicorn tracea.server.main:app --host 0.0.0.0 --port 8080 --workers 1
```

Or in the background:

```bash
export $(grep -v '^#' .env | xargs)
uvicorn tracea.server.main:app --host 0.0.0.0 --port 8080 --workers 1 > /tmp/tracea.log 2>&1 &
```

### Dashboard

The dashboard is served automatically by FastAPI at `http://localhost:8080/dashboard/` after you build it:

```bash
cd dashboard
npm run build
```

For dashboard development with hot reload:

```bash
cd dashboard
npm run dev
# Opens on http://localhost:5173
```

### Docker

```bash
docker-compose up --build
```

The server starts on port 8080, persists data to `./data/`, and the dashboard is available at `http://localhost:8080/dashboard/`.

---

## Detection Rules

Rules are written in YAML and hot-reloaded on save. Edit them in Settings → `detection_rules.yaml`.

Example rule:

```yaml
rules:
  - id: high_cost
    description: "Individual call cost exceeds $0.05"
    condition:
      field: cost_usd
      op: gt
      value: 0.05
    issue_category: high_cost
    severity: high
```

Supported operators: `eq`, `equals`, `ne`, `gt`, `gte`, `lt`, `lte`, `contains`, `starts_with`, `exists`

Composite conditions with `and` / `or` and repetition detection are also supported.

---

## Alerts

Alert routing is configured in Settings → `alerts.yaml`:

```yaml
routes:
  - issue_category: tool_error
    route_type: slack
    webhook_url: "${SLACK_WEBHOOK_URL}"
    rate_limit_rpm: 60
```

Use `issue_category: "*"` as a catch-all fallback.

---

## RCA Setup

Enable AI-powered root cause analysis by setting an LLM backend in `.env`:

**OpenAI:**
```bash
TRACEA_RCA_BACKEND=openai
OPENAI_API_KEY=sk-...
```

**Anthropic:**
```bash
TRACEA_RCA_BACKEND=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

**Anthropic-compatible proxy (e.g., MiniMax):**
```bash
TRACEA_RCA_BACKEND=anthropic
ANTHROPIC_API_KEY=your-key
ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic
TRACEA_RCA_MODEL=MiniMax-M2.7
```

**Ollama (local, free):**
```bash
TRACEA_RCA_BACKEND=ollama
TRACEA_RCA_BASE_URL=http://localhost:11434
TRACEA_RCA_MODEL=llama3
```

---

## API

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /api/v1/sessions` | List sessions |
| `GET /api/v1/sessions/{id}/events` | Session events |
| `GET /api/v1/issues` | List issues |
| `GET /api/v1/config/rules` | Read detection rules YAML |
| `PUT /api/v1/config/rules` | Write detection rules YAML |
| `GET /api/v1/config/alerts` | Read alerts YAML |
| `PUT /api/v1/config/alerts` | Write alerts YAML |

All API endpoints require `Authorization: Bearer {api_key}` (unless `TRACEA_DEV_MODE=1` is set).

---

## Development

```bash
# Run backend tests
pytest tests/

# Run dashboard build
cd dashboard && npm run build

# Run SDK tests
cd sdk-python && pytest

# Run MCP tests
cd tracea-mcp && pytest
```

---

## License

MIT
