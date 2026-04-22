# tracea Python SDK

Self-hosted AI agent observability SDK. Automatically intercept LLM calls via httpx patching, or log events directly with fire-and-forget helpers.

## Installation

```bash
pip install tracea
```

Or from source:

```bash
cd sdk-python
pip install -e "."
```

## Quick Start

### One-line init (auto-patches httpx)

```python
import tracea

# Initialize — this patches httpx to intercept OpenAI, Anthropic, etc.
tracea.init(api_key="your-api-key", server_url="http://localhost:8080")

# All LLM calls are now automatically traced
import openai
client = openai.OpenAI()
response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": "hi"}])
# ^ This call is automatically logged to tracea
```

### Session-scoped tracing

```python
import tracea
import asyncio

tracea.init(api_key="your-api-key")

async def main():
    async with tracea.session(metadata={"user_id": "123"}, agent_id="my-bot"):
        # All events inside this block share the same session_id
        response = client.chat.completions.create(...)

asyncio.run(main())
```

### Direct event logging (fire-and-forget)

For tool calls, custom events, or non-httpx LLM calls:

```python
import tracea

tracea.init(api_key="your-api-key")

# Log a tool call
tracea.log_tool_call("search", {"query": "python"})

# Log the result
tracea.log_tool_result("search", result={"hits": [...]}, duration_ms=120)

# Log a chat message (for local models, custom transports, etc.)
tracea.log_chat(role="assistant", content="Hello!", model="gpt-4o")

# Log an error
tracea.log_error("Database connection failed")

# Log a fully custom event
tracea.log_event("custom.event", content="something happened", metadata={"foo": "bar"})
```

### Auto-timed tool calls with context manager

```python
import tracea

with tracea.LogTool("search", arguments={"query": "python"}) as lt:
    # Your tool code here
    lt.result = do_search("python")
    # On exit: tool_result event is emitted with elapsed duration

# If an exception is raised inside the block, it's captured as an error event
```

## Configuration

| Parameter | Env Var | Default | Description |
|-----------|---------|---------|-------------|
| `api_key` | `TRACEA_API_KEY` | — | Required. Your tracea API key. |
| `server_url` | `TRACEA_SERVER_URL` | `http://localhost:8080` | tracea server URL. |
| `base_url` | `TRACEA_BASE_URL` | `server_url` | Base URL for LLM API calls (Azure, proxies). |
| `metadata` | — | `{}` | Global metadata applied to all events. |
| `tags` | — | `[]` | Global tags applied to all events. |

## Session context

The `tracea.session()` context manager:
- Derives a deterministic `session_id` from hostname + PID
- Emits `session_start` on enter and `session_end` on exit
- Attaches `metadata`, `tags`, and `agent_id` to all events in the block

```python
async with tracea.session(
    metadata={"deployment": "prod", "version": "1.2.3"},
    tags=["important"],
    agent_id="customer-support-bot",
):
    # Events here are tagged and attributed
    ...
```

## Patching existing clients

If you construct an LLM client before calling `tracea.init()`, you can patch it explicitly:

```python
import openai
client = openai.OpenAI()

import tracea
tracea.init(api_key="...")

# Patch the already-constructed client
tracea.patch_client(client)
```

## Event types

The SDK emits these event types automatically:

| Event Type | Source | Description |
|------------|--------|-------------|
| `session_start` | `tracea.session()` | Session begins |
| `chat.completion` | httpx patch | LLM API call |
| `tool_call` | `log_tool_call()` / `LogTool` | Tool invocation |
| `tool_result` | `log_tool_result()` / `LogTool` | Tool completion |
| `error` | `log_error()` / exception | Error occurred |
| `session_end` | `tracea.session()` | Session ends |

## Buffering & offline support

Events are batched in memory (50 events or 1 second) and flushed to the tracea server. If the server is unreachable, events overflow to a local SQLite disk buffer (`~/.tracea/buffer.db`) and are replayed on reconnect.

## API Reference

### `tracea.init(api_key, server_url, base_url, metadata, tags)`
Initialize the SDK. Must be called once. Auto-patches httpx.

### `tracea.session(metadata, tags, agent_id, session_id, emit_events)`
Async context manager for session-scoped tracing.

### `tracea.log_tool_call(tool_name, arguments, tool_call_id, metadata)`
Fire-and-forget tool call event.

### `tracea.log_tool_result(tool_name, result, error, duration_ms, tool_call_id, metadata)`
Fire-and-forget tool result event.

### `tracea.log_chat(role, content, model, provider, metadata)`
Fire-and-forget chat message event.

### `tracea.log_error(error, metadata)`
Fire-and-forget error event.

### `tracea.log_event(event_type, content, metadata, **kwargs)`
Fire-and-forget custom event.

### `tracea.LogTool(tool_name, arguments, tool_call_id, metadata)`
Context manager for auto-timed tool calls.

### `tracea.patch_client(client, base_url)`
Patch an already-constructed LLM client.
