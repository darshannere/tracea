"""httpx transport-level patching for tracea SDK."""
from __future__ import annotations
import httpx
import time
import asyncio
from typing import Any, Optional
from uuid import uuid4
from tracea.patch._utils import detect_provider
from tracea.session import get_session_ctx
from tracea.events import TracedEvent, TokenUsage, EventType, Provider

_original_sync_send: Any = None
_original_async_send: Any = None
_is_patched: bool = False

# Per-session sequence counters
_sequence_counters: dict[str, int] = {}

def _get_next_sequence(session_id: str) -> int:
    global _sequence_counters
    if session_id not in _sequence_counters:
        _sequence_counters[session_id] = 0
    _sequence_counters[session_id] += 1
    return _sequence_counters[session_id]

def _is_llm_request(request: httpx.Request, client: httpx.BaseClient | None = None) -> bool:
    """Return True if this request is an LLM API call to patch.

    Args:
        request: The httpx request object.
        client: Optional httpx client instance. If the client has a
                 _tracea_base_url attribute (set via patch_client(base_url=...)),
                 the path is extracted by stripping that base URL from the
                 full request URL. This is needed for Azure OpenAI and other
                 proxied endpoints where the httpx client has a custom
                 base_url that contains the deployment path prefix.
    """
    url_str = str(request.url)

    # If client has a stored per-client base URL, use it to extract the effective path
    if client is not None and hasattr(client, "_tracea_base_url"):
        base_url = client._tracea_base_url.rstrip("/")
        if base_url and url_str.startswith(base_url):
            url_str = url_str[len(base_url):]

    provider = detect_provider(url_str)
    return provider != "unknown"

def _build_event(
    request: httpx.Request,
    response: httpx.Response | None,
    duration_ms: int,
    error: str | None,
    stream_content: str | None,
) -> TracedEvent:
    """Build a TracedEvent from captured request/response data."""
    from datetime import datetime, timezone
    from tracea.config import get_config

    try:
        config = get_config()
    except RuntimeError:
        config = None

    ctx = get_session_ctx()
    session_id = ctx.get("session_id") or str(uuid4())
    provider = detect_provider(str(request.url))

    # Extract model from request URL or body
    model = _extract_model(request, response)

    # Extract status code
    status_code = response.status_code if response else None

    # Extract content
    content = None
    if stream_content:
        content = stream_content
    elif response and not response.is_stream_consumed:
        content = response.text

    # Extract token usage and cost
    tokens_used = None
    cost_usd = None
    if response:
        usage = _extract_usage(response)
        if usage:
            tokens_used = TokenUsage(
                input=usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0),
                output=usage.get("output_tokens", 0) or usage.get("completion_tokens", 0),
                total=usage.get("total_tokens", 0),
            )
            cost_usd = _estimate_cost(provider, model, tokens_used)

    return TracedEvent(
        event_id=uuid4(),
        session_id=session_id,
        agent_id=ctx.get("agent_id", ""),
        sequence=_get_next_sequence(session_id),
        timestamp=datetime.now(timezone.utc),
        type="chat.completion",
        provider=provider,
        model=model,
        content=content,
        status_code=status_code,
        error=error,
        duration_ms=duration_ms,
        tokens_used=tokens_used,
        cost_usd=cost_usd,
        metadata=ctx.get("metadata", {}),
    )

def _extract_model(request: httpx.Request, response: httpx.Response | None) -> str:
    """Extract model name from request URL or body."""
    # Try URL first (common pattern: /v1/chat/models/gpt-4o)
    path_parts = request.url.path.split("/")
    for i, part in enumerate(path_parts):
        if part == "models" and i + 1 < len(path_parts):
            return path_parts[i + 1]
    # Try request body
    try:
        body = request.read().decode("utf-8")
        import json
        data = json.loads(body)
        return data.get("model", "")
    except Exception:
        return ""

def _extract_usage(response: httpx.Response) -> dict | None:
    """Extract token usage from response JSON."""
    try:
        if response.is_stream_consumed:
            return None
        data = response.json()
        return data.get("usage") or data.get("anthropic_reasoning")  # anthropic uses different shape
    except Exception:
        return None

def _estimate_cost(provider: str, model: str, tokens: TokenUsage) -> float | None:
    """Estimate USD cost from token usage. Returns None if cannot estimate."""
    if tokens and tokens.total > 0:
        # Very rough estimation — actual costs vary by provider/model
        return round(tokens.total * 0.00001, 6)  # ~$0.01/1K tokens rough avg
    return None

def _emit_event(event: TracedEvent) -> None:
    """Emit event to buffer. Calls async buffer.add() from sync httpx send path.

    When called from sync code within an active asyncio context (e.g., pytest),
    run the async add() in a background thread with its own event loop and wait
    for it to complete before returning. This ensures the event is in the buffer
    when flush_now() is called after the sync API call returns.

    When called with no active event loop, use asyncio.run() directly.
    """
    try:
        from tracea.buffer import get_buffer
        buffer = get_buffer()
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is not None:
            # Called from sync code within an active asyncio context.
            # Run in a background thread with its own event loop, then block
            # the calling thread until the add() completes.
            import threading
            result_holder = [None, None]  # [event, exception]

            def _thread_target():
                event_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(event_loop)
                try:
                    event_loop.run_until_complete(buffer.add(event))
                except Exception as exc:
                    result_holder[1] = exc
                finally:
                    event_loop.close()

            thread = threading.Thread(target=_thread_target, daemon=True)
            thread.start()
            thread.join()  # Block until the thread completes
            if result_holder[1] is not None:
                raise result_holder[1]
        else:
            # No running loop — use asyncio.run()
            asyncio.run(buffer.add(event))
    except Exception as exc:
        import logging
        logging.getLogger("tracea").error(f"_emit_event failed: {exc}")

def _patched_sync_send(self, request: httpx.Request, **kwargs) -> httpx.Response:
    """Patched httpx.Client.send — sync path."""
    global _original_sync_send

    if not _is_llm_request(request, client=self):
        return _original_sync_send(self, request, **kwargs)

    start = time.monotonic()
    try:
        response = _original_sync_send(self, request, **kwargs)
        duration_ms = int((time.monotonic() - start) * 1000)

        # Handle streaming
        if _is_streaming_response(request, response):
            response = _wrap_sync_stream_response(response, request, duration_ms)
        else:
            # Non-streaming: emit immediately after response is complete
            event = _build_event(request, response, duration_ms, error=None, stream_content=None)
            _emit_event(event)

        return response
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        event = _build_event(request, None, duration_ms, error=str(exc), stream_content=None)
        _emit_event(event)
        raise

async def _patched_async_send(self, request: httpx.Request, **kwargs) -> httpx.Response:
    """Patched httpx.AsyncClient.send — async path."""
    global _original_async_send

    if not _is_llm_request(request, client=self):
        return await _original_async_send(self, request, **kwargs)

    start = time.monotonic()
    try:
        response = await _original_async_send(self, request, **kwargs)
        duration_ms = int((time.monotonic() - start) * 1000)

        if _is_streaming_response(request, response):
            response = await _wrap_async_stream_response(response, request, duration_ms)
        else:
            event = _build_event(request, response, duration_ms, error=None, stream_content=None)
            _emit_event(event)

        return response
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        event = _build_event(request, None, duration_ms, error=str(exc), stream_content=None)
        _emit_event(event)
        raise

def _is_streaming_response(request: httpx.Request, response: httpx.Response) -> bool:
    """Detect if request expects a streaming response."""
    # Check request body for stream: true
    try:
        body = request.read().decode("utf-8")
        import json
        data = json.loads(body)
        return data.get("stream", False) is True
    except Exception:
        return False

def _wrap_sync_stream_response(response: httpx.Response, request: httpx.Request, duration_ms: int) -> httpx.Response:
    """Wrap a sync streaming response to accumulate content and emit event on exhaust."""
    original_iter = response.iter_lines

    content_parts: list[str] = []

    def collecting_iter():
        for line in original_iter():
            content_parts.append(line)
            yield line
        # Stream exhausted — emit event
        full_content = "\n".join(content_parts)
        event = _build_event(request, response, duration_ms, error=None, stream_content=full_content)
        _emit_event(event)

    response.stream_lines = collecting_iter  # type: ignore
    # Replace iter_lines to return our wrapper
    response.iter_lines = collecting_iter  # type: ignore
    return response

async def _wrap_async_stream_response(response: httpx.Response, request: httpx.Request, duration_ms: int) -> httpx.Response:
    """Wrap an async streaming response to accumulate content and emit event on exhaust."""
    original_aiter = response.aiter_lines()

    content_parts: list[str] = []

    async def collecting_aiter():
        async for line in original_aiter:
            content_parts.append(line)
            yield line
        # Stream exhausted — emit event
        full_content = "\n".join(content_parts)
        event = _build_event(request, response, duration_ms, error=None, stream_content=full_content)
        _emit_event(event)

    # Replace aiter_lines to return our wrapper
    response.aiter_lines = collecting_aiter  # type: ignore
    return response

def patch() -> None:
    """Install class-level patches on httpx.Client and httpx.AsyncClient.

    Idempotent — safe to call multiple times.
    """
    global _original_sync_send, _original_async_send, _is_patched

    if _is_patched:
        return

    _original_sync_send = httpx.Client.send
    _original_async_send = httpx.AsyncClient.send

    httpx.Client.send = _patched_sync_send  # type: ignore
    httpx.AsyncClient.send = _patched_async_send  # type: ignore

    _is_patched = True

def unpatch() -> None:
    """Restore original httpx send methods."""
    global _original_sync_send, _original_async_send, _is_patched

    if not _is_patched:
        return

    if _original_sync_send is not None:
        httpx.Client.send = _original_sync_send  # type: ignore
    if _original_async_send is not None:
        httpx.AsyncClient.send = _original_async_send  # type: ignore

    _is_patched = False
