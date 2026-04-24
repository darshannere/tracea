# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-04-24

### Added

- **Server**: FastAPI backend with SQLite WAL, batched event ingestion, session tracking, and background retention
- **Python SDK**: Auto-instrumentation via httpx patching for OpenAI, Anthropic, and Azure OpenAI; BatchBuffer + DiskBuffer for zero event loss
- **Dashboard**: React 18 + Vite SPA with session list, event timeline, issue cards, cost/token charts (Recharts), and settings editor
- **Detection Engine**: YAML-configurable rule engine with 13 seed rules (tool errors, high cost, high latency, rate limits, infinite loops, etc.); hot-reload via filesystem watcher
- **RCA Worker**: Async LLM-powered root cause analysis with backends for OpenAI, Anthropic, and Ollama; configurable prompt templates and content redaction
- **Alert Dispatcher**: Slack Block Kit and generic HTTP webhook routing with deduplication, per-destination rate limiting, exponential backoff retry, and dead-letter table
- **MCP Server**: stdio JSON-RPC transport for Claude Code, Cursor, Cline, and Zed integration
- **Agent Plugins**: Native lifecycle hook plugins for Claude Code, Gemini CLI, Kimi CLI, OpenCode, and OpenClaw
- **Config API**: Runtime read/write of `detection_rules.yaml` and `alerts.yaml` with atomic writes and hot-reload

### Security

- Bearer token auth with `secrets.compare_digest()` to prevent timing attacks
- Dev mode (`TRACEA_DEV_MODE=1`) for local development — disabled by default
- API key auto-generation on first boot with POSIX locking verification

### Notes

- TypeScript SDK is planned for v0.2.0
- GitHub issue auto-creation is planned for v0.2.0
