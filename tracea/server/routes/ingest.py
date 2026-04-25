from fastapi import APIRouter, HTTPException
from tracea.server.models import EventBatch
from tracea.server.db import enqueue_events, flush_events
import asyncio
from tracea.server.detection.engine import run_detection

router = APIRouter(prefix="/api/v1", tags=["ingest"])

_MAX_BATCH_SIZE = 1000


@router.post("/events")
async def ingest_events(
    batch: EventBatch,
) -> dict:
    if len(batch.events) > _MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=413,
            detail={"error": "batch_too_large", "max": _MAX_BATCH_SIZE, "received": len(batch.events)}
        )
    await enqueue_events(batch.events)
    await flush_events()

    # Fire detection AFTER commit
    asyncio.create_task(run_detection(batch.events))

    return {"accepted": len(batch.events)}


@router.post("/events/mcp")
async def ingest_mcp_events(
    batch: EventBatch,
) -> dict:
    """Ingest events from tracea-mcp (Claude Code / OpenClaw integration).

    Marks all events with integration=tracea-mcp metadata.
    """
    if len(batch.events) > _MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=413,
            detail={"error": "batch_too_large", "max": _MAX_BATCH_SIZE, "received": len(batch.events)}
        )
    for event in batch.events:
        if event.metadata is None:
            event.metadata = {}
        event.metadata["integration"] = "tracea-mcp"

    await enqueue_events(batch.events)
    await flush_events()
    asyncio.create_task(run_detection(batch.events))

    return {"accepted": len(batch.events)}