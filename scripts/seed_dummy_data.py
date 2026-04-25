#!/usr/bin/env python3
"""Seed tracea with realistic dummy data for demo/testing."""
import asyncio
import json
import random
import uuid
from datetime import datetime, timedelta, timezone

import httpx

SERVER_URL = "http://localhost:8080"
USERS = ["alice", "bob", "charlie"]
AGENTS = ["claude-code", "kimi", "openclaw", "gemini-cli"]
TOOLS = ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "SearchWeb", "FetchURL"]
MODELS = ["gpt-4o", "claude-sonnet-4-20250514", "gemini-2.5-pro"]


def random_time_in_last(days=3):
    """Return a random ISO timestamp within the last N days."""
    now = datetime.now(timezone.utc)
    delta = timedelta(
        days=random.randint(0, days),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
        seconds=random.randint(0, 59),
    )
    return (now - delta).isoformat().replace("+00:00", "Z")


def _offset(base_iso, seconds):
    base = datetime.fromisoformat(base_iso.replace("Z", "+00:00"))
    return (base + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def make_tokens():
    """Generate consistent token usage where input + output == total."""
    inp = random.randint(50, 800)
    out = random.randint(50, 1200)
    return {"input": inp, "output": out, "total": inp + out}


def make_session(user, agent):
    """Generate a complete session with events for one user."""
    session_id = str(uuid.uuid4())
    sequence = 0
    events = []

    # session_start
    sequence += 1
    start_ts = random_time_in_last(5)
    events.append({
        "event_id": str(uuid.uuid4()),
        "session_id": session_id,
        "agent_id": agent,
        "user_id": user,
        "sequence": sequence,
        "timestamp": start_ts,
        "type": "session_start",
        "provider": agent,
        "model": "",
        "duration_ms": 0,
        "metadata": {"source": agent, "integration": "tracea-mcp"},
    })

    num_turns = random.randint(2, 8)
    for _ in range(num_turns):
        # chat.completion (user prompt)
        sequence += 1
        toks = make_tokens()
        events.append({
            "event_id": str(uuid.uuid4()),
            "session_id": session_id,
            "agent_id": agent,
            "user_id": user,
            "sequence": sequence,
            "timestamp": _offset(start_ts, sequence * 3),
            "type": "chat.completion",
            "provider": agent,
            "model": random.choice(MODELS),
            "role": "user",
            "content": "How do I " + random.choice(["refactor this", "optimize that", "debug the error", "write tests for"]),
            "duration_ms": random.randint(200, 1200),
            "tokens_used": toks,
            "cost_usd": round(random.uniform(0.001, 0.02), 6),
            "metadata": {},
        })

        # Maybe a tool call
        if random.random() > 0.3:
            tool = random.choice(TOOLS)
            tool_call_id = str(uuid.uuid4())

            sequence += 1
            events.append({
                "event_id": str(uuid.uuid4()),
                "session_id": session_id,
                "agent_id": agent,
                "user_id": user,
                "sequence": sequence,
                "timestamp": _offset(start_ts, sequence * 3 + 1),
                "type": "tool_call",
                "provider": agent,
                "tool_name": tool,
                "tool_call_id": tool_call_id,
                "content": json.dumps({"query": "python"}),
                "duration_ms": 0,
                "metadata": {},
            })

            # tool_result
            has_error = random.random() < 0.15
            sequence += 1
            events.append({
                "event_id": str(uuid.uuid4()),
                "session_id": session_id,
                "agent_id": agent,
                "user_id": user,
                "sequence": sequence,
                "timestamp": _offset(start_ts, sequence * 3 + 2),
                "type": "error" if has_error else "tool_result",
                "provider": agent,
                "tool_name": tool,
                "tool_call_id": tool_call_id,
                "content": "Error: connection timeout" if has_error else json.dumps({"result": "ok"}),
                "status_code": 500 if has_error else 200,
                "error": "connection timeout" if has_error else None,
                "duration_ms": random.randint(100, 3000),
                "metadata": {},
            })

        # Sometimes a high-cost chat.completion (assistant response)
        if random.random() > 0.2:
            sequence += 1
            toks = make_tokens()
            events.append({
                "event_id": str(uuid.uuid4()),
                "session_id": session_id,
                "agent_id": agent,
                "user_id": user,
                "sequence": sequence,
                "timestamp": _offset(start_ts, sequence * 3 + 1),
                "type": "chat.completion",
                "provider": agent,
                "model": random.choice(MODELS),
                "role": "assistant",
                "content": "Here is the solution you requested...",
                "duration_ms": random.randint(500, 3000),
                "tokens_used": toks,
                "cost_usd": round(random.uniform(0.005, 0.05), 6),
                "metadata": {},
            })

    # session_end
    sequence += 1
    events.append({
        "event_id": str(uuid.uuid4()),
        "session_id": session_id,
        "agent_id": agent,
        "user_id": user,
        "sequence": sequence,
        "timestamp": _offset(start_ts, sequence * 3 + 5),
        "type": "session_end",
        "provider": agent,
        "duration_ms": 0,
        "metadata": {},
    })

    return events


async def post_events(client, events):
    resp = await client.post(f"{SERVER_URL}/api/v1/events", json={"events": events})
    if resp.status_code != 200:
        print(f"ERROR {resp.status_code}: {resp.text[:500]}")
    resp.raise_for_status()
    return resp.json()


async def main():
    async with httpx.AsyncClient(timeout=30.0) as client:
        all_events = []
        for user in USERS:
            for _ in range(random.randint(4, 7)):
                agent = random.choice(AGENTS)
                session_events = make_session(user, agent)
                all_events.extend(session_events)

        # Shuffle slightly so batches are mixed
        random.shuffle(all_events)

        # Post in batches of 100
        batch_size = 100
        for i in range(0, len(all_events), batch_size):
            batch = all_events[i:i + batch_size]
            result = await post_events(client, batch)
            print(f"Posted batch {i // batch_size + 1}: {result}")

        print(f"\nDone! Posted {len(all_events)} events across {len(USERS)} users.")


if __name__ == "__main__":
    asyncio.run(main())
