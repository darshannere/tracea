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

def _is_llm_request(request: httpx.Request) -> bool:
    """Return True if this request is an LLM API call to patch."""
    provider = detect_provider(str(request.url))
    return provider != "unknown"

def _build_event(
    request: httpx.Request,
    response: httpx.Response | None,
    duration_ms: int,
    error: str | None,
    stream_content: str | None,
) -> TracedEvent:
    """Build a TracedEvent from captured request/response data."""
    from datetime import datetime
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
        timestamp=datetime.utcnow(),
        type=EventType("chat.completion"),
        provider=Provider(provider),
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
    """Emit event to buffer. Deferred import to avoid circular deps."""
    try:
        from tracea.buffer import get_buffer
        get_buffer().add(event)
    except (ImportError, RuntimeError):
        # Buffer not yet initialized — log for debugging
        import logging
        logging.getLogger("tracea").debug(f"Event: {event}")

def _patched_sync_send(self, request: httpx.Request, **kwargs) -> httpx.Response:
    """Patched httpx.Client.send — sync path."""
    global _original_sync_send

    if not _is_llm_request(request):
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

    if not _is_llm_request(request):
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
