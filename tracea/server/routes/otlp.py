from __future__ import annotations
import json
from fastapi import APIRouter, Request, Depends, HTTPException, Response

from tracea.server.otel import parser
from tracea.server.auth import otlp_auth

router = APIRouter(tags=["otlp"])

# Cap OTLP request bodies at 16 MiB. A single OTLP payload can carry many
# spans/logs/metrics, but an unbounded read lets a misbehaving exporter OOM
# the server.
_MAX_OTLP_BODY_BYTES = 16 * 1024 * 1024


async def _read_body(request: Request) -> bytes:
    """Read the request body with a hard size cap."""
    body = await request.body()
    if len(body) > _MAX_OTLP_BODY_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"OTLP payload too large ({len(body)} > {_MAX_OTLP_BODY_BYTES} bytes)",
        )
    return body


def _decode_content_type(request: Request) -> str:
    ct = request.headers.get("content-type", "application/json").lower()
    return ct


def _empty_response(signal: str, content_type: str) -> Response:
    """Build an empty Export{Signal}ServiceResponse in the requested encoding."""
    if "protobuf" in content_type:
        if signal == "traces":
            from opentelemetry.proto.collector.trace.v1 import trace_service_pb2 as pb
        elif signal == "logs":
            from opentelemetry.proto.collector.logs.v1 import logs_service_pb2 as pb
        else:
            from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2 as pb
        body = pb.ExportTraceServiceResponse().SerializeToString() if signal == "traces" \
            else (pb.ExportLogsServiceResponse().SerializeToString() if signal == "logs"
                  else pb.ExportMetricsServiceResponse().SerializeToString())
        return Response(content=body, media_type="application/x-protobuf")
    # JSON
    return Response(content="{}", media_type="application/json")


@router.post("/v1/traces")
async def otlp_traces(
    request: Request,
    user_id: str = Depends(otlp_auth),
) -> Response:
    body = await _read_body(request)
    content_type = _decode_content_type(request)
    try:
        spans = parser.parse_traces(body, content_type)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse OTLP traces: {exc}")

    # Persist spans (Task 6 adds enqueue_spans). For now, tolerate no-op if
    # the helper isn't wired yet — but Task 3 MUST call it so the integration
    # test in Task 8 sees data.
    from tracea.server.otel.mapper import spans_to_events_and_persist
    await spans_to_events_and_persist(spans, user_id)

    return _empty_response("traces", content_type)


@router.post("/v1/logs")
async def otlp_logs(
    request: Request,
    user_id: str = Depends(otlp_auth),
) -> Response:
    body = await _read_body(request)
    content_type = _decode_content_type(request)
    try:
        logs = parser.parse_logs(body, content_type)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse OTLP logs: {exc}")

    # Map logs → events (Tasks 4-5). The mapper returns TracedEvent list.
    from tracea.server.otel.mapper import logs_to_events
    events = logs_to_events(logs, user_id)
    if events:
        from tracea.server.db import enqueue_events, flush_events
        from tracea.server.routes.ingest import _validate_user_ids
        # OTLP path: same user_id validation as HTTP ingest (H13).
        await _validate_user_ids(events)
        await enqueue_events(events)
        await flush_events()
        # Fire detection async, same as the MCP ingest path
        import asyncio
        from tracea.server.detection.engine import run_detection
        from tracea.server.detection.watcher import track_task
        track_task(asyncio.create_task(run_detection(events)))

    return _empty_response("logs", content_type)


@router.post("/v1/metrics")
async def otlp_metrics(
    request: Request,
    user_id: str = Depends(otlp_auth),
) -> Response:
    body = await _read_body(request)
    content_type = _decode_content_type(request)
    try:
        metrics = parser.parse_metrics(body, content_type)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse OTLP metrics: {exc}")

    # Task 7 adds enqueue_metrics. Call it inline here.
    from tracea.server.otel.mapper import persist_metrics
    await persist_metrics(metrics, user_id)

    return _empty_response("metrics", content_type)
