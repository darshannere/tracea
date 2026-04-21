# tracea

Self-hosted AI agent observability platform. Trace LLM sessions, detect issues, get AI-powered root cause analysis, and route alerts — all in one place.

## Features

- **Session Tracking** — Automatically trace LLM calls, tool executions, errors, and session lifecycle
- **Real-time Dashboard** — React dashboard with insights visualizations: cost trends, token usage, duration distribution, session health, and more
- **Issue Detection** — YAML-configurable detection rules for tool errors, high cost, high latency, rate limits, repeated calls, infinite loops, and more
- **AI-Powered RCA** — Root cause analysis powered by LLMs (OpenAI, Anthropic, or local Ollama)
- **Alert Routing** — Route issues to Slack or generic webhooks with per-destination rate limiting
- **SDK + MCP** — Python SDK for manual tracing and MCP server for Claude Code / OpenClaw integration

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
│   └── src/
│       ├── pages/          # Sessions, Issues, Settings
│       └── components/     # Charts, layout, settings
├── sdk-python/             # Python SDK for manual tracing
├── tracea-mcp/             # MCP server for Claude Code integration
├── data/                   # SQLite database (created at runtime)
├── docker-compose.yml      # Docker deployment
└── .env.example            # Env var template
```

## Prerequisites

- Python 3.11+
- Node.js 20+ (for dashboard dev)
- SQLite 3.45+ (for WAL mode)

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
```

### 3. Python SDK (optional)

```bash
cd sdk-python
pip install -e "."
```

### 4. MCP Server (optional)

```bash
cd tracea-mcp
pip install -e "."
```

## Configuration

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

Key variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `TRACEA_DB_PATH` | SQLite database path | `./data/tracea.db` |
| `TRACEA_RULES_PATH` | Detection rules YAML | `./tracea/server/detection/defaults/detection_rules.yaml` |
| `TRACEA_ALERTS_PATH` | Alerts routing YAML | `./tracea/server/alerts.yaml` |
| `TRACEA_RCA_BACKEND` | RCA LLM backend: `disabled`, `openai`, `anthropic`, `ollama` | `disabled` |
| `TRACEA_RCA_MODEL` | Model to use for RCA | backend default |
| `TRACEA_RCA_BASE_URL` | Custom base URL (for Ollama or proxies) | — |
| `OPENAI_API_KEY` | Required if using OpenAI RCA | — |
| `ANTHROPIC_API_KEY` | Required if using Anthropic RCA | — |

## Running

### Backend

```bash
# Load env vars and start server
export $(grep -v '^#' .env | xargs)
uvicorn tracea.server.main:app --host 0.0.0.0 --port 8080
```

Or in the background:

```bash
export $(grep -v '^#' .env | xargs)
uvicorn tracea.server.main:app --host 0.0.0.0 --port 8080 > /tmp/tracea.log 2>&1 &
```

The server will:
- Start on `http://localhost:8080`
- Auto-generate an API key on first run (printed to console)
- Load default detection rules if none exist
- Start the RCA background worker (if configured)
- Poll for new issues every 5 seconds

### Dashboard

```bash
cd dashboard
npm run dev
```

Open `http://localhost:5173`. Paste the API key from the server console into the auth prompt.

### Docker

```bash
docker-compose up --build
```

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

All API endpoints require `Authorization: Bearer {api_key}`.

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

## License

MIT
