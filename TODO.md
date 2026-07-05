# Production Cleanup TODO

From repo-wide audit (2026-07-05). Ranked biggest cut first.
Net estimate: ~-2,000 lines, -8 deps.

## Cuts

- [x] **Delete tracea-mcp shadow toolset** — `tools/bash.py`, `read`, `write`, `edit`, `glob`, `grepc` (~400 lines) re-implement Claude Code's native tools inside an observability MCP. No agent routes its Bash through a replica; README already says hooks are the real integration; a remote bash/write/edit executor in a pip package is a liability. Keep `log_to_tracea` + brain tool only. (`base.py`+`registry.py` are shared infra, not replicas — reuse or drop with the package flatten below.) [`tracea-mcp/src/tracea_mcp/tools/`]
- [x] **Retire the observagent compat API** — 371 lines under `/api/v1/observagent/*` + migration `008_observagent_support` carry the dead product name into production. Note the file already exposes `/api/v1/observagent/insights/*` (7 endpoints) — the work is *drop the `observagent` segment* and relocate `/events` + `/sessions`, not a green-field rename. Update the dashboard URLs to match. [`tracea/server/routes/observagent.py`]
- [x] **Deduplicate the 4 forked plugins** — kimi/gemini hooks are ~90% identical Python; opencode/openclaw are forked TS. Every fix currently ships 4×. Generate single-file installs from one shared core. [`tracea-plugins/`]
- [x] **Replace monaco-editor with a textarea** — multi-MB editor bundle for one YAML textbox; validate server-side on save. −1 heavy dep. [`dashboard/src/components/settings/YamlEditor.tsx`]
- [x] **Remove 5 unused Radix packages** — checkbox, dialog, label, scroll-area, toast have zero imports (sonner handles toasts). −5 deps. [`dashboard/package.json`]
- [x] **Drop axios for native fetch** — used in exactly one file. −1 dep. [`dashboard/src/lib/api.ts`]
- [x] **Flatten alerts/** — 7 files / 500 lines for "POST a webhook with retry" (router, dispatcher, watcher, formatters, models, backoff). Two files (~250 lines) hold the same logic. [`tracea/server/alerts/`]
- [x] **Shrink backoff.py 43→~10 lines** — the "async" version awaits nothing; both functions just compute `min(base*2**attempt, cap) + jitter`. One sync function (keep the signature + docstring, drop the duplicate body). [`tracea/server/alerts/backoff.py`]
- [x] **Merge RCA backends** — OllamaBackend and OpenAIBackend are byte-identical except URL/headers → one OpenAI-compatible backend. `DisabledBackend` → `backend is None`. Delete dead `context` param in every `analyze()`. **Scope separately:** `AnthropicBackend` uses a different API shape (Messages API, content blocks, `x-api-key`) and won't fold in for free — real refactor, not a rename. ~60 lines for the Ollama/OpenAI merge; +budget for Anthropic. [`tracea/server/rca/backends.py`]
- [x] **Use ON DELETE CASCADE for retention** — `foreign_keys=ON` is already set; declare cascades and retention becomes one `DELETE FROM sessions WHERE started_at < ?`. Bind the cutoff, don't f-string it. **Caveat:** SQLite pragmas are per-connection; `rca/worker.py:213 _open_db()` opens a fresh connection without setting `foreign_keys=ON`, so cascade won't apply to anything the worker writes. Set the pragma in `_open_db()` or stop opening separate connections. [`tracea/server/main.py:22`]
- [x] **Batch settings reads** — `get_brain_config` fires 12 sequential SELECTs every 5s poll; same pattern in `get_rca_config`. One `SELECT key, value WHERE key IN (...)`. [`tracea/server/settings.py`]
- [x] **Consolidate the two LLM polling workers** — RCA + Brain each have their own 5s loop, config loader, backend loader, lifecycle globals. One generic worker parameterized twice. Fix `_POLLO_INTERVAL` typo. [`tracea/server/rca/worker.py:14`]
- [x] **Flatten tracea-mcp packages** — `transport/`, `client/`, `tools/` sub-packages with 1–4-line `__init__.py`s for a ~700-line program → 3 flat modules. [`tracea-mcp/src/tracea_mcp/`]
- [x] **Delete `create_app()`** — factory that returns the module-level singleton and configures nothing. [`tracea/server/main.py:95`]
- [x] **Purge root scratch** — `run_detection.py`, `tracea-mcp/_t.py`, `darshannere-main-design-*.md`, `dashboard-current.md`, 6 root PNGs, `landing/` (only 3 screenshots), untracked `AGENTS.md` + `scripts/seed_rca.py`. Move `tests/seed_and_verify.py` (722-line script, not a test) to `scripts/` so pytest stops collecting it.
- [x] **Kill `data/api_key.txt`** — stray 44-byte plaintext file in the data dir; move all key input to env vars only. (See the plaintext-keys item in Broken — that's the real problem.) [`data/api_key.txt`]

## Broken — fix pass (not bloat, actual defects)

- [x] **Detection dedup is per-boot in-memory** — `_processed_event_ids` / `_recent_by_session` grow unbounded AND reset on restart (wrong twice). `run_detection.py` exists only because detection isn't replayable. Make it idempotent in the DB (unique index on `issues(rule_id, event_id)` or a processed flag); the leak and the script both disappear. [`tracea/server/detection/engine.py:11-14`]
- [x] **Health check lies** — `/health` hardcodes `"db": "ok"` without touching the DB. Add a `SELECT 1`. [`tracea/server/main.py:67`]
- [x] **Write buffer unprotected** — `enqueue_events` appends to `_write_buffer` outside `_write_lock`; flush loop runs forever even when idle. Works only because asyncio is single-threaded today. [`tracea/server/db.py:161`]
- [x] **Session upsert re-aggregates the full events table per session on every flush** — O(session size) per 500ms flush; first long-running session makes ingest crawl. At minimum add a `ponytail:` ceiling comment; better, maintain incremental totals. [`tracea/server/db.py:230`]
- [x] **`get_db()` is a DI costume on a global** — async generator yielding a singleton, consumed two different ways: `await anext(get_db())` (observagent.py, main.py) vs. `db_gen = get_db(); await db_gen.__anext__()` (engine.py, settings.py). Either real FastAPI `Depends` or plain `get_db() -> Connection`. Pick one and standardize the call sites too. [`tracea/server/db.py:50`]
- [x] **Plaintext LLM keys in SQLite (CWE-922/312)** — the `settings` table stores `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` in cleartext (`settings.py:47-48,83-84`), and `data/tracea.db` (13MB) sits in the repo data dir. Anyone with DB/file access reads the LLM keys. Real fix, not "note it": OS keyring, env-only, or encrypt-at-rest. [`tracea/server/settings.py`]

## Decide first

The two decisions that shape everything else: kill the MCP shadow toolset, and settle the observagent naming. Do those before the mechanical cleanups.

One sequencing note: **fix the detection dedup (Broken) before purging `run_detection.py` (Cuts)** — the script only exists because detection isn't replayable, so making detection idempotent in the DB deletes the script's reason to exist and closes the memory leak in one move.
