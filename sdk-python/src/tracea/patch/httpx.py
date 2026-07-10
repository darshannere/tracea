"""httpx transport-level patching for tracea SDK."""
from __future__ import annotations
import httpx
import time
import asyncio
import queue
import threading
import atexit
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

# Background worker for async event emission — never blocks the caller.
_emit_queue: queue.Queue = queue.Queue()
_worker_thread: threading.Thread | None = None
_worker_stop = threading.Event()
_queue_drain_event = threading.Event()
_queue_drain_event.set()


def _worker_loop() -> None:
    """Background thread: drains queue, runs async buffer.add() in own loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        while not _worker_stop.is_set():
            try:
                event = _emit_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                from tracea.buffer import get_buffer
                buffer = get_buffer()
                loop.run_until_complete(buffer.add(event))
            except Exception as exc:
                import logging
                logging.getLogger("tracea").error(f"_worker_loop failed: {exc}")
            finally:
                _emit_queue.task_done()
    finally:
        loop.close()


def _start_worker() -> None:
    """Ensure the background worker thread is running."""
    global _worker_thread
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    _worker_stop.clear()
    _worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="tracea-emit-worker")
    _worker_thread.start()


def _stop_worker() -> None:
    """Stop the worker (called at exit)."""
    _worker_stop.set()
    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=2.0)


# Register atexit to flush on normal interpreter shutdown
atexit.register(_stop_worker)


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

    # Extract content — read the body ONCE into a local and reuse for both
    # content and usage. A try/except (rather than an is_stream_consumed guard)
    # is used because buffered responses (incl. test mocks) may report
    # is_stream_consumed=True while still exposing a readable body; and a
    # genuinely consumed streaming response will raise, which we safely skip.
    content = None
    body_text: str | None = None
    if stream_content:
        content = stream_content
    elif response:
        try:
            body_text = response.text
            content = body_text
        except Exception:
            body_text = None

    # Extract token usage and cost (from the already-read body_text, not response.json())
    tokens_used = None
    cost_usd = None
    if response and body_text:
        usage = _extract_usage_from_text(body_text)
        if usage:
            input_t = usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0)
            output_t = usage.get("output_tokens", 0) or usage.get("completion_tokens", 0)
            # Anthropic responses don't include total_tokens — compute it.
            # OpenAI includes it; fall back to input + output if absent/zero.
            total_t = usage.get("total_tokens") or (input_t + output_t)
            tokens_used = TokenUsage(
                input=input_t,
                output=output_t,
                total=total_t,
            )
            cost_usd = _estimate_cost(provider, model, tokens_used)

    return TracedEvent(
        event_id=uuid4(),
        session_id=session_id,
        agent_id=ctx.get("agent_id") or (config.agent_id if config else ""),
        user_id=config.user_id if config else "",
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
        metadata={**ctx.get("metadata", {}), **(config.metadata if config else {})},
    )

def _extract_model(request: httpx.Request, response: httpx.Response | None) -> str:
    """Extract model name from request URL or body."""
    from tracea.patch._utils import extract_azure_deployment
    
    # Try URL first (common pattern: /v1/chat/models/gpt-4o)
    path_parts = request.url.path.split("/")
    for i, part in enumerate(path_parts):
        if part == "models" and i + 1 < len(path_parts):
            return path_parts[i + 1]
    
    # Try Azure deployment path: /openai/deployments/{deployment}/...
    azure_deployment = extract_azure_deployment(request.url.path)
    if azure_deployment:
        return azure_deployment
    
    # Try request body
    try:
        body = request.read().decode("utf-8")
        import json
        data = json.loads(body)
        return data.get("model", "")
    except Exception:
        return ""

def _extract_usage_from_text(body_text: str) -> dict | None:
    """Extract token usage from response body text."""
    try:
        import json
        data = json.loads(body_text)
        return data.get("usage") or data.get("anthropic_reasoning")  # anthropic uses different shape
    except Exception:
        return None

def _extract_usage(response: httpx.Response) -> dict | None:
    """Extract token usage from response JSON (backwards-compatible wrapper)."""
    try:
        return _extract_usage_from_text(response.text)
    except Exception:
        return None

def _estimate_cost(provider: str, model: str, tokens: TokenUsage) -> float | None:
    """Estimate USD cost from token usage. Returns None if cannot estimate."""
    if tokens and tokens.total > 0:
        # Very rough estimation — actual costs vary by provider/model
        return round(tokens.total * 0.00001, 6)  # ~$0.01/1K tokens rough avg
    return None

def _emit_event(event: TracedEvent) -> None:
    """Emit event to buffer. Non-blocking — pushes to queue for background worker.

    The background worker processes the queue and calls buffer.add() in its own
    event loop, so the caller's thread is never blocked.
    """
    _start_worker()
    _queue_drain_event.clear()
    try:
        _emit_queue.put_nowait(event)
    except queue.Full:
        import logging
        logging.getLogger("tracea").warning("Event queue full, dropping event")


def drain_queue(timeout: float = 2.0) -> bool:
    """Wait for all queued events to be processed by the background worker.

    Returns True if the queue is empty within the timeout, False if still pending.
    Used by tests and shutdown paths to ensure events reach the buffer.
    """
    _emit_queue.join()
    # Give the worker time to actually add events to the buffer
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _emit_queue.empty():
            return True
        time.sleep(0.01)
    return _emit_queue.empty()

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
    """Wrap a sync streaming response to accumulate content and emit event on exhaust.

    Wraps ``iter_bytes`` (not ``iter_lines``) because the OpenAI / Anthropic
    SDKs consume the streaming body via httpcore's raw byte stream, bypassing
    ``iter_lines`` entirely. The captured bytes are parsed as SSE frames to
    reconstruct the assistant message content and final usage.
    """
    original_iter_bytes = response.iter_bytes

    collected: list[bytes] = []

    def collecting_iter_bytes():
        for chunk in original_iter_bytes():
            collected.append(chunk)
            yield chunk
        # Stream exhausted — reconstruct and emit
        raw = b"".join(collected)
        content, usage = _parse_sse_stream(raw)
        event = _build_stream_event(request, response, duration_ms, content, usage)
        _emit_event(event)

    response.iter_bytes = collecting_iter_bytes  # type: ignore[method-assign]
    # Also re-point iter_lines / aiter_* to the byte wrapper for callers that
    # iterate line-by-line — they will still see the same bytes.
    response.iter_lines = collecting_iter_bytes  # type: ignore[method-assign]
    return response

async def _wrap_async_stream_response(response: httpx.Response, request: httpx.Request, duration_ms: int) -> httpx.Response:
    """Wrap an async streaming response to accumulate content and emit event on exhaust."""
    original_aiter_bytes = response.aiter_bytes

    collected: list[bytes] = []

    async def collecting_aiter_bytes():
        async for chunk in original_aiter_bytes():
            collected.append(chunk)
            yield chunk
        raw = b"".join(collected)
        content, usage = _parse_sse_stream(raw)
        event = _build_stream_event(request, response, duration_ms, content, usage)
        _emit_event(event)

    response.aiter_bytes = collecting_aiter_bytes  # type: ignore[method-assign]
    response.aiter_lines = collecting_aiter_bytes  # type: ignore[method-assign]
    return response


def _parse_sse_stream(raw: bytes) -> tuple[str, dict | None]:
    """Parse an SSE byte stream into (assistant_text, usage_dict_or_None).

    Handles OpenAI's ``data: {...}\\n\\n`` framing (terminated by ``data: [DONE]``)
    and Anthropic's event-typed SSE (``event: content_block_delta`` etc.).
    """
    if not raw:
        return "", None
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        return "", None

    import json
    content_parts: list[str] = []
    usage: dict | None = None

    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]" or payload == "":
            continue
        try:
            evt = json.loads(payload)
        except Exception:
            continue
        # OpenAI chat completion chunk
        choices = evt.get("choices") or []
        if choices:
            delta = choices[0].get("delta") or {}
            piece = delta.get("content")
            if piece:
                content_parts.append(piece)
        # OpenAI streaming usage (when stream_options.include_usage=true)
        if evt.get("usage"):
            u = evt["usage"]
            usage = {
                "input_tokens": u.get("prompt_tokens", 0),
                "output_tokens": u.get("completion_tokens", 0),
                "total_tokens": u.get("total_tokens", 0),
            }
        # Anthropic message_delta / message_start usage
        if evt.get("type") == "content_block_delta":
            delta = evt.get("delta") or {}
            if delta.get("type") == "text_delta":
                content_parts.append(delta.get("text", ""))
        if evt.get("type") == "message_delta":
            u = (evt.get("usage") or {})
            if u:
                usage = usage or {}
                usage["output_tokens"] = u.get("output_tokens", usage.get("output_tokens", 0))
                if "input_tokens" in u:
                    usage["input_tokens"] = u["input_tokens"]
        if evt.get("type") == "message_start":
            msg = evt.get("message") or {}
            u = msg.get("usage") or {}
            if u:
                usage = {
                    "input_tokens": u.get("input_tokens", 0),
                    "output_tokens": u.get("output_tokens", 0),
                }

    # Anthropic total is input + output
    if usage and not usage.get("total_tokens"):
        usage["total_tokens"] = (usage.get("input_tokens", 0) or 0) + (usage.get("output_tokens", 0) or 0)

    return "".join(content_parts), usage


def _build_stream_event(request, response, duration_ms, content, usage):
    """Build a TracedEvent for a completed streaming response."""
    event = _build_event(request, response, duration_ms, error=None, stream_content=content)
    # If we parsed usage, overwrite the (empty) tokens from _build_event.
    if usage:
        from tracea.events import TokenUsage
        event.tokens_used = TokenUsage(
            input=usage.get("input_tokens", 0),
            output=usage.get("output_tokens", 0),
            total=usage.get("total_tokens") or (usage.get("input_tokens", 0) + usage.get("output_tokens", 0)),
        )
        event.cost_usd = _estimate_cost(event.provider, event.model, event.tokens_used)
    return event

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
