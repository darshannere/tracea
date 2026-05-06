"""
Tracea Test Data Suite — seed realistic sessions for all users and verify
every tab is connected end-to-end.

Usage:
    # Seed data + full verification (requires running server at localhost:8080):
    python tests/seed_and_verify.py

    # Start server automatically, then seed + verify:
    python tests/seed_and_verify.py --start-server

    # Verify only (no seeding — use after a previous seed run):
    python tests/seed_and_verify.py --verify-only

    # Seed only (no verification):
    python tests/seed_and_verify.py --seed-only

What gets created:
    - 9 sessions across 3 users × 3 agents (claude-code, cursor, gemini-cli)
    - 80+ events: session_start, chat.completion, tool_call, tool_result,
                  error, session_end (all valid EventTypes)
    - Issues fired by: tool_error, task_failure, high_cost, high_latency,
                      empty_response, model_error_5xx, rate_limit_hit
    - 5 brain entries seeded directly (3 categories: workflow, error_fix, codebase)

Tabs verified:
    Sessions, Agents, Issues, Live (observagent), Brain
"""

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx

BASE_URL = "http://localhost:8080"
DB_PATH = Path(__file__).parent.parent / "data" / "tracea.db"

# All users already in the DB
USERS = ["darshann", "alice", "darshan"]

# Agent/provider pairs: (agent_id, provider, model)
AGENTS = [
    ("claude-code",  "anthropic",  "claude-sonnet-4-5"),
    ("cursor",       "openai",     "gpt-4o"),
    ("gemini-cli",   "openai",     "gemini-2.0-flash"),
]

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _ts(offset_seconds: float = 0) -> str:
    """ISO 8601 UTC timestamp, optionally offset from now."""
    t = datetime.now(tz=timezone.utc) + timedelta(seconds=offset_seconds)
    return t.isoformat().replace("+00:00", "Z")


def _ev(
    *,
    session_id: str,
    agent_id: str,
    user_id: str,
    seq: int,
    ev_type: str,
    provider: str = "openai",
    model: str = "gpt-4o",
    content: str = "",
    tool_name: str = "",
    tool_call_id: str = "",
    error: str = "",
    status_code: int | None = None,
    duration_ms: int = 800,
    cost_usd: float | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    offset_s: float = 0,
    metadata: dict | None = None,
) -> dict:
    """Build a single event dict ready for the EventBatch payload."""
    ev: dict = {
        "event_id": str(uuid4()),
        "session_id": session_id,
        "agent_id": agent_id,
        "user_id": user_id,
        "sequence": seq,
        "timestamp": _ts(offset_s),
        "type": ev_type,
        "provider": provider,
        "model": model,
        "duration_ms": duration_ms,
        "metadata": metadata or {},
    }
    if content:
        ev["content"] = content
    if tool_name:
        ev["tool_name"] = tool_name
    if tool_call_id:
        ev["tool_call_id"] = tool_call_id
    if error:
        ev["error"] = error
    if status_code is not None:
        ev["status_code"] = status_code
    if cost_usd is not None:
        ev["cost_usd"] = cost_usd
    if input_tokens or output_tokens:
        ev["tokens_used"] = {
            "input": input_tokens,
            "output": output_tokens,
            "total": input_tokens + output_tokens,
        }
    return ev


def _post(client: httpx.Client, events: list[dict]) -> dict:
    resp = client.post(
        f"{BASE_URL}/api/v1/events",
        json={"events": events},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


# ──────────────────────────────────────────────────────────────────────────────
# Session builders
# ──────────────────────────────────────────────────────────────────────────────

def build_clean_session(user_id: str, agent_id: str, provider: str, model: str) -> tuple[str, list[dict]]:
    """
    Normal successful session: start → 4 tool round-trips → 2 completions → end.
    No detection rules should fire.
    """
    sid = str(uuid4())
    evs = [
        _ev(session_id=sid, agent_id=agent_id, user_id=user_id, seq=1,
            ev_type="session_start", provider=provider, model=model, offset_s=-120),

        # tool_call 1
        _ev(session_id=sid, agent_id=agent_id, user_id=user_id, seq=2,
            ev_type="tool_call", provider=provider, model=model,
            tool_name="Bash", tool_call_id=str(uuid4()),
            content="ls -la tracea/server/", duration_ms=45, offset_s=-110),
        # tool_result 1
        _ev(session_id=sid, agent_id=agent_id, user_id=user_id, seq=3,
            ev_type="tool_result", provider=provider, model=model,
            tool_name="Bash", content="main.py  db.py  routes/  models.py", duration_ms=40, offset_s=-105),

        # tool_call 2
        _ev(session_id=sid, agent_id=agent_id, user_id=user_id, seq=4,
            ev_type="tool_call", provider=provider, model=model,
            tool_name="Read", tool_call_id=str(uuid4()),
            content="tracea/server/main.py", duration_ms=30, offset_s=-100),
        # tool_result 2
        _ev(session_id=sid, agent_id=agent_id, user_id=user_id, seq=5,
            ev_type="tool_result", provider=provider, model=model,
            tool_name="Read", content="import fastapi\napp = create_app()", duration_ms=25, offset_s=-95),

        # tool_call 3
        _ev(session_id=sid, agent_id=agent_id, user_id=user_id, seq=6,
            ev_type="tool_call", provider=provider, model=model,
            tool_name="Edit", tool_call_id=str(uuid4()),
            content="Fix auth import in main.py", duration_ms=55, offset_s=-90),
        # tool_result 3
        _ev(session_id=sid, agent_id=agent_id, user_id=user_id, seq=7,
            ev_type="tool_result", provider=provider, model=model,
            tool_name="Edit", content="Edit applied successfully.", duration_ms=50, offset_s=-85),

        # tool_call 4
        _ev(session_id=sid, agent_id=agent_id, user_id=user_id, seq=8,
            ev_type="tool_call", provider=provider, model=model,
            tool_name="Bash", tool_call_id=str(uuid4()),
            content="pytest tests/ -x -q", duration_ms=2100, offset_s=-80),
        # tool_result 4
        _ev(session_id=sid, agent_id=agent_id, user_id=user_id, seq=9,
            ev_type="tool_result", provider=provider, model=model,
            tool_name="Bash", content="4 passed in 0.92s", duration_ms=2090, offset_s=-78),

        # chat.completion 1
        _ev(session_id=sid, agent_id=agent_id, user_id=user_id, seq=10,
            ev_type="chat.completion", provider=provider, model=model,
            content="I've fixed the auth import and confirmed tests pass.",
            duration_ms=1200, cost_usd=0.018, input_tokens=420, output_tokens=85, offset_s=-70),

        # chat.completion 2
        _ev(session_id=sid, agent_id=agent_id, user_id=user_id, seq=11,
            ev_type="chat.completion", provider=provider, model=model,
            content="The codebase looks healthy. All routes are wired correctly.",
            duration_ms=980, cost_usd=0.012, input_tokens=310, output_tokens=62, offset_s=-65),

        _ev(session_id=sid, agent_id=agent_id, user_id=user_id, seq=12,
            ev_type="session_end", provider=provider, model=model, offset_s=-60),
    ]
    return sid, evs


def build_issues_session(user_id: str, agent_id: str, provider: str, model: str) -> tuple[str, list[dict]]:
    """
    Session that fires every detection rule:
      - tool_error    (error field set on a chat.completion)
      - task_failure  (event type = 'error')
      - high_cost     (cost_usd > $0.05)
      - high_latency  (duration_ms > 30000)
      - empty_response (chat.completion with empty content)
      - model_error_5xx (status_code 503)
      - rate_limit_hit  (status_code 429)
    """
    sid = str(uuid4())
    evs = [
        _ev(session_id=sid, agent_id=agent_id, user_id=user_id, seq=1,
            ev_type="session_start", provider=provider, model=model, offset_s=-300),

        # Tool call that triggers tool_error (error field on result)
        _ev(session_id=sid, agent_id=agent_id, user_id=user_id, seq=2,
            ev_type="tool_call", provider=provider, model=model,
            tool_name="Bash", tool_call_id=str(uuid4()),
            content="npm run build", duration_ms=500, offset_s=-295),
        _ev(session_id=sid, agent_id=agent_id, user_id=user_id, seq=3,
            ev_type="tool_result", provider=provider, model=model,
            tool_name="Bash",
            error="Build failed: Cannot find module '@/components/layout'",
            content="", duration_ms=490, offset_s=-290),

        # chat.completion → triggers high_cost ($0.12 > $0.05)
        _ev(session_id=sid, agent_id=agent_id, user_id=user_id, seq=4,
            ev_type="chat.completion", provider=provider, model=model,
            content="Let me analyze the build failure in detail.",
            cost_usd=0.12, input_tokens=2800, output_tokens=350,
            duration_ms=4200, offset_s=-280),

        # chat.completion → triggers empty_response (empty content)
        _ev(session_id=sid, agent_id=agent_id, user_id=user_id, seq=5,
            ev_type="chat.completion", provider=provider, model=model,
            content="", cost_usd=0.002, duration_ms=310, offset_s=-270),

        # chat.completion → triggers high_latency (duration > 30s)
        _ev(session_id=sid, agent_id=agent_id, user_id=user_id, seq=6,
            ev_type="chat.completion", provider=provider, model=model,
            content="Taking a long time to think...",
            cost_usd=0.03, duration_ms=35000, offset_s=-240),

        # event type = 'error' → triggers task_failure
        _ev(session_id=sid, agent_id=agent_id, user_id=user_id, seq=7,
            ev_type="error", provider=provider, model=model,
            error="Agent crashed: uncaught exception in tool handler",
            duration_ms=0, offset_s=-200),

        # status_code 503 → triggers model_error_5xx
        _ev(session_id=sid, agent_id=agent_id, user_id=user_id, seq=8,
            ev_type="chat.completion", provider=provider, model=model,
            content="", status_code=503,
            error="Service Unavailable", duration_ms=250, offset_s=-195),

        # status_code 429 → triggers rate_limit_hit
        _ev(session_id=sid, agent_id=agent_id, user_id=user_id, seq=9,
            ev_type="chat.completion", provider=provider, model=model,
            content="", status_code=429,
            error="Rate limit exceeded. Retry after 60s.", duration_ms=120, offset_s=-190),

        _ev(session_id=sid, agent_id=agent_id, user_id=user_id, seq=10,
            ev_type="session_end", provider=provider, model=model, offset_s=-180),
    ]
    return sid, evs


def build_long_session(user_id: str, agent_id: str, provider: str, model: str) -> tuple[str, list[dict]]:
    """
    Longer session with many tool calls — exercises the Live tab tool log
    and brain synthesis event count threshold.
    """
    sid = str(uuid4())
    tools = ["Bash", "Read", "Edit", "Write", "WebSearch", "Glob", "Grep"]
    evs = [
        _ev(session_id=sid, agent_id=agent_id, user_id=user_id, seq=1,
            ev_type="session_start", provider=provider, model=model, offset_s=-600),
    ]
    seq = 2
    for i, tool in enumerate(tools * 2):  # 14 tool round-trips
        offset = -590 + i * 35
        tcid = str(uuid4())
        evs.append(_ev(
            session_id=sid, agent_id=agent_id, user_id=user_id, seq=seq,
            ev_type="tool_call", provider=provider, model=model,
            tool_name=tool, tool_call_id=tcid,
            content=f"Running {tool} task #{i+1}",
            duration_ms=400 + i * 50, offset_s=offset,
        ))
        seq += 1
        evs.append(_ev(
            session_id=sid, agent_id=agent_id, user_id=user_id, seq=seq,
            ev_type="tool_result", provider=provider, model=model,
            tool_name=tool, tool_call_id=tcid,
            content=f"Result of {tool} task #{i+1}: OK",
            duration_ms=390 + i * 50, offset_s=offset + 15,
        ))
        seq += 1

    # Add 3 chat.completions
    for i in range(3):
        evs.append(_ev(
            session_id=sid, agent_id=agent_id, user_id=user_id, seq=seq,
            ev_type="chat.completion", provider=provider, model=model,
            content=f"Progress checkpoint {i+1}: tasks proceeding as expected.",
            cost_usd=0.015 + i * 0.005, input_tokens=380 + i * 50,
            output_tokens=70 + i * 10, duration_ms=1100 + i * 200,
            offset_s=-600 + 100 + i * 60,
        ))
        seq += 1

    evs.append(_ev(
        session_id=sid, agent_id=agent_id, user_id=user_id, seq=seq,
        ev_type="session_end", provider=provider, model=model, offset_s=-50,
    ))
    return sid, evs


# ──────────────────────────────────────────────────────────────────────────────
# Brain entry seeder (direct SQL — LLM backend disabled)
# ──────────────────────────────────────────────────────────────────────────────

def _brain_id(category: str, title: str) -> str:
    key = f"{category}|{title.lower().strip()}"
    return hashlib.sha256(key.encode()).hexdigest()


BRAIN_ENTRIES = [
    {
        "category": "workflow",
        "title": "Bash tool for file exploration",
        "content": (
            "## Pattern\n"
            "Use `ls -la <dir>` to list files, then `Read` to inspect specific files. "
            "Avoid `cat` — the `Read` tool is more token-efficient.\n\n"
            "## When to use\nAt the start of a task when the directory structure is unknown.\n\n"
            "## Example\n```bash\nls -la tracea/server/\n```\nThen `Read tracea/server/main.py`."
        ),
        "confidence": 0.85,
        "hit_count": 3,
    },
    {
        "category": "workflow",
        "title": "Multi-step code analysis then edit pattern",
        "content": (
            "## Pattern\n"
            "1. `Bash` to list directory\n"
            "2. `Read` the relevant file\n"
            "3. `Edit` for targeted changes\n"
            "4. `Bash` to run tests\n\n"
            "## Why\nMinimises context usage vs reading entire file. "
            "Tests after edit confirm nothing regressed."
        ),
        "confidence": 0.72,
        "hit_count": 2,
    },
    {
        "category": "error_fix",
        "title": "Rate limit handling with exponential backoff",
        "content": (
            "## Error\n`429 Too Many Requests` from OpenAI or Anthropic.\n\n"
            "## Fix\nWrap the API call with retry logic:\n"
            "```python\nimport time, random\nfor attempt in range(5):\n"
            "    try:\n        return call_api()\n"
            "    except RateLimitError:\n"
            "        time.sleep((2 ** attempt) + random.random())\n```\n\n"
            "## Root cause\nBurst traffic exceeding the tier's RPM limit."
        ),
        "confidence": 0.90,
        "hit_count": 4,
    },
    {
        "category": "error_fix",
        "title": "Empty response recovery strategy",
        "content": (
            "## Error\nModel returns empty `content` on `chat.completion`.\n\n"
            "## Fix\n"
            "1. Check `stop_reason` — `max_tokens` means truncation, increase `max_tokens`.\n"
            "2. If `stop_reason` is `end_turn`, retry once with a higher temperature.\n"
            "3. If still empty, log the prompt and escalate.\n\n"
            "## Prevention\nAdd a guard: `assert response.content, 'Empty completion'`."
        ),
        "confidence": 0.65,
        "hit_count": 2,
    },
    {
        "category": "codebase",
        "title": "Tracea event ingestion architecture",
        "content": (
            "## Flow\n"
            "`POST /api/v1/events` → `enqueue_events()` → `flush_events()` "
            "→ SQLite `events` + `sessions` upsert → `run_detection()` async.\n\n"
            "## Key files\n"
            "- `tracea/server/routes/ingest.py` — HTTP handler\n"
            "- `tracea/server/db.py::flush_events` — bulk write + session upsert\n"
            "- `tracea/server/detection/engine.py` — rule evaluation\n\n"
            "## Notes\n"
            "`flush_events` re-aggregates the full session from the events table "
            "so partial batches don't produce stale totals."
        ),
        "confidence": 0.78,
        "hit_count": 3,
    },
]


def seed_brain_entries(session_ids: list[str]) -> int:
    """Insert brain entries directly into SQLite (LLM backend is disabled)."""
    import sqlite3

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Rotate through the session_ids we just created as source evidence
    inserted = 0
    for i, entry in enumerate(BRAIN_ENTRIES):
        eid = _brain_id(entry["category"], entry["title"])
        # Use a subset of session_ids as sources
        sources = session_ids[i % len(session_ids) : i % len(session_ids) + 2]
        if not sources:
            sources = session_ids[:1]

        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO brain_entries
                    (id, user_id, category, title, content, confidence, source_sessions, hit_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    eid,
                    USERS[i % len(USERS)],
                    entry["category"],
                    entry["title"],
                    entry["content"],
                    entry["confidence"],
                    json.dumps(sources),
                    entry["hit_count"],
                ),
            )
            inserted += 1
        except Exception as e:
            print(f"  [brain] Failed to insert '{entry['title']}': {e}")

    conn.commit()
    conn.close()
    return inserted


# ──────────────────────────────────────────────────────────────────────────────
# Server management
# ──────────────────────────────────────────────────────────────────────────────

_server_proc = None


def start_server() -> subprocess.Popen:
    global _server_proc
    print("Starting tracea server on :8080 …")
    _server_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tracea.server.main:app",
         "--host", "127.0.0.1", "--port", "8080", "--workers", "1"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(Path(__file__).parent.parent),
    )
    # Wait until /health responds
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            r = httpx.get(f"{BASE_URL}/health", timeout=2)
            if r.status_code == 200:
                print("  Server ready.")
                return _server_proc
        except Exception:
            pass
        time.sleep(0.5)
    _server_proc.terminate()
    raise RuntimeError("Server did not start within 15s")


def stop_server() -> None:
    global _server_proc
    if _server_proc:
        _server_proc.terminate()
        _server_proc = None


# ──────────────────────────────────────────────────────────────────────────────
# Seeding
# ──────────────────────────────────────────────────────────────────────────────

def seed_all() -> list[str]:
    """POST test events for every user×agent combo. Returns all new session_ids."""
    all_session_ids: list[str] = []
    total_events = 0

    with httpx.Client() as client:
        for user_id in USERS:
            print(f"\n  User: {user_id}")
            for agent_id, provider, model in AGENTS:
                # Session A — clean
                sid_a, evs_a = build_clean_session(user_id, agent_id, provider, model)
                r = _post(client, evs_a)
                print(f"    [{agent_id}] clean session    → {sid_a[:8]}… accepted={r['accepted']}")
                all_session_ids.append(sid_a)
                total_events += r["accepted"]

                # Session B — issues
                sid_b, evs_b = build_issues_session(user_id, agent_id, provider, model)
                r = _post(client, evs_b)
                print(f"    [{agent_id}] issues session   → {sid_b[:8]}… accepted={r['accepted']}")
                all_session_ids.append(sid_b)
                total_events += r["accepted"]

                # Session C — long / many tool calls
                sid_c, evs_c = build_long_session(user_id, agent_id, provider, model)
                r = _post(client, evs_c)
                print(f"    [{agent_id}] long session     → {sid_c[:8]}… accepted={r['accepted']}")
                all_session_ids.append(sid_c)
                total_events += r["accepted"]

    print(f"\n  Total: {len(all_session_ids)} sessions, {total_events} events ingested.")
    return all_session_ids


# ──────────────────────────────────────────────────────────────────────────────
# Verification
# ──────────────────────────────────────────────────────────────────────────────

PASS = "✅ PASS"
FAIL = "❌ FAIL"
WARN = "⚠️  WARN"

def _check(label: str, condition: bool, detail: str = "") -> bool:
    status = PASS if condition else FAIL
    print(f"  {status}  {label}" + (f"  ({detail})" if detail else ""))
    return condition


def verify_all() -> bool:
    """Hit every API endpoint used by each dashboard tab and report status."""
    results: list[bool] = []
    client = httpx.Client(base_url=BASE_URL, timeout=10)

    print("\n── Sessions tab (/api/v1/sessions) ──────────────────────────────")
    r = client.get("/api/v1/sessions")
    ok = r.status_code == 200
    results.append(_check("GET /api/v1/sessions returns 200", ok, f"status={r.status_code}"))
    if ok:
        data = r.json()
        sessions = data.get("sessions", [])
        results.append(_check("sessions array is non-empty", len(sessions) > 0, f"count={len(sessions)}"))
        users_in_sessions = {s.get("user_id") for s in sessions if s.get("user_id")}
        for uid in USERS:
            results.append(_check(f"user '{uid}' has sessions", uid in users_in_sessions))
        has_ended = any(s.get("ended_at") for s in sessions)
        results.append(_check("at least one session has ended_at set", has_ended))
        has_cost = any((s.get("total_cost") or 0) > 0 for s in sessions)
        results.append(_check("at least one session has total_cost > 0", has_cost))

    print("\n── Agents tab (/api/v1/agents) ──────────────────────────────────")
    r = client.get("/api/v1/agents")
    ok = r.status_code == 200
    results.append(_check("GET /api/v1/agents returns 200", ok))
    if ok:
        data = r.json()
        agents = data.get("agents", [])
        results.append(_check("agents array is non-empty", len(agents) > 0, f"count={len(agents)}"))
        agent_ids = {a["agent_id"] for a in agents}
        for aid, _, _ in AGENTS:
            results.append(_check(f"agent '{aid}' appears", aid in agent_ids))
        has_platform = any(a.get("platform") for a in agents)
        results.append(_check("at least one agent has platform set", has_platform))

    print("\n── Agents tab — Users (/api/v1/users) ───────────────────────────")
    r = client.get("/api/v1/users")
    ok = r.status_code == 200
    results.append(_check("GET /api/v1/users returns 200", ok))
    if ok:
        data = r.json()
        users = {u["user_id"] for u in data.get("users", [])}
        for uid in USERS:
            results.append(_check(f"user '{uid}' in users table", uid in users))

    print("\n── Issues tab (/api/v1/issues) ───────────────────────────────────")
    r = client.get("/api/v1/issues")
    ok = r.status_code == 200
    results.append(_check("GET /api/v1/issues returns 200", ok))
    if ok:
        data = r.json()
        issues = data.get("issues", [])
        results.append(_check("issues array is non-empty", len(issues) > 0, f"count={len(issues)}"))
        rule_ids = {i.get("rule_id") for i in issues}
        for expected_rule in ["tool_error", "task_failure", "high_cost", "high_latency",
                               "empty_response", "model_error_5xx", "rate_limit_hit"]:
            results.append(_check(f"rule '{expected_rule}' fired", expected_rule in rule_ids))

    print("\n── Live tab (/api/v1/observagent/*) ─────────────────────────────")
    r = client.get("/api/v1/observagent/events?limit=50")
    ok = r.status_code == 200
    results.append(_check("GET /api/v1/observagent/events returns 200", ok))
    if ok:
        evs = r.json()
        results.append(_check("observagent events is non-empty", len(evs) > 0, f"count={len(evs)}"))

    r = client.get("/api/v1/observagent/sessions")
    ok = r.status_code == 200
    results.append(_check("GET /api/v1/observagent/sessions returns 200", ok))
    if ok:
        data = r.json()
        obs_sessions = data.get("sessions", [])
        results.append(_check("observagent sessions is non-empty", len(obs_sessions) > 0, f"count={len(obs_sessions)}"))

    r = client.get("/api/v1/observagent/health")
    ok = r.status_code == 200
    results.append(_check("GET /api/v1/observagent/health returns 200", ok))

    print("\n── Brain tab (/api/v1/brain/*) ───────────────────────────────────")
    r = client.get("/api/v1/brain/entries")
    ok = r.status_code == 200
    results.append(_check("GET /api/v1/brain/entries returns 200", ok))
    if ok:
        data = r.json()
        entries = data.get("entries", [])
        total = data.get("total", 0)
        results.append(_check("brain entries is non-empty", len(entries) > 0, f"total={total}"))
        categories = {e["category"] for e in entries}
        for cat in ["workflow", "error_fix", "codebase"]:
            results.append(_check(f"brain category '{cat}' present", cat in categories))

    r = client.get("/api/v1/brain/graph")
    ok = r.status_code == 200
    results.append(_check("GET /api/v1/brain/graph returns 200", ok))
    if ok:
        data = r.json()
        nodes = data.get("nodes", [])
        results.append(_check("brain graph has nodes", len(nodes) > 0, f"nodes={len(nodes)}"))

    print("\n── Brain FTS search ─────────────────────────────────────────────")
    r = client.get("/api/v1/brain/entries?q=rate+limit")
    ok = r.status_code == 200
    results.append(_check("FTS search 'rate limit' returns 200", ok))
    if ok:
        data = r.json()
        results.append(_check("FTS search finds the rate-limit entry",
                               data.get("total", 0) > 0, f"total={data.get('total', 0)}"))

    client.close()

    passed = sum(1 for x in results if x)
    failed = len(results) - passed
    print(f"\n{'─'*60}")
    print(f"Verification: {passed}/{len(results)} checks passed  ({failed} failed)")
    if failed == 0:
        print("ALL CHECKS PASSED — every tab is connected and populated.")
    else:
        print(f"{failed} check(s) FAILED — see above for details.")
    return failed == 0


# ──────────────────────────────────────────────────────────────────────────────
# Entrypoint
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Tracea test data suite")
    parser.add_argument("--start-server", action="store_true",
                        help="Start the uvicorn server before running")
    parser.add_argument("--verify-only", action="store_true",
                        help="Skip seeding; only run verification")
    parser.add_argument("--seed-only", action="store_true",
                        help="Seed data but skip verification")
    args = parser.parse_args()

    if args.start_server:
        start_server()

    try:
        # Confirm server is reachable
        try:
            httpx.get(f"{BASE_URL}/health", timeout=3).raise_for_status()
        except Exception:
            print(f"ERROR: Server not reachable at {BASE_URL}")
            print("  Run with --start-server, or start it manually:")
            print("  python -m uvicorn tracea.server.main:app --port 8080")
            sys.exit(1)

        session_ids: list[str] = []

        if not args.verify_only:
            print(f"\n{'─'*60}")
            print("SEEDING test data …")
            print(f"{'─'*60}")
            session_ids = seed_all()

            # Give detection engine a moment to process async tasks
            print("\nWaiting 2s for detection engine to process issues …")
            time.sleep(2)

            print("\nSeeding brain entries (direct SQL — LLM backend disabled) …")
            n = seed_brain_entries(session_ids)
            print(f"  Inserted {n} brain entries.")

        if not args.seed_only:
            print(f"\n{'─'*60}")
            print("VERIFYING all tabs …")
            print(f"{'─'*60}")
            ok = verify_all()
            sys.exit(0 if ok else 1)

    finally:
        if args.start_server:
            stop_server()


if __name__ == "__main__":
    main()
