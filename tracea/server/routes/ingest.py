from fastapi import APIRouter, HTTPException, Depends
from tracea.server.models import EventBatch
from tracea.server.db import enqueue_events, flush_events, get_db
from tracea.server.auth import get_auth_user_id
import asyncio
from tracea.server.detection.engine import run_detection

router = APIRouter(prefix="/api/v1", tags=["ingest"])

_MAX_BATCH_SIZE = 1000


@router.post("/events")
async def ingest_events(
    batch: EventBatch,
    auth_user_id: str = Depends(get_auth_user_id),
) -> dict:
    if len(batch.events) > _MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=413,
            detail={"error": "batch_too_large", "max": _MAX_BATCH_SIZE, "received": len(batch.events)}
        )

    # Inject user_id from authenticated API key if event lacks one
    for event in batch.events:
        if not event.user_id and auth_user_id:
            event.user_id = auth_user_id

    # Validate non-empty user_ids against users table
    unique_user_ids = {e.user_id for e in batch.events if e.user_id}
    if unique_user_ids:
        db = await anext(get_db())
        placeholders = ",".join("?" for _ in unique_user_ids)
        rows = await db.execute(
            f"SELECT user_id FROM users WHERE user_id IN ({placeholders})",
            tuple(unique_user_ids),
        )
        found = {r["user_id"] for r in await rows.fetchall()}
        unknown = unique_user_ids - found
        if unknown:
            raise HTTPException(
                status_code=400,
                detail={"error": "unknown_user_ids", "unknown": sorted(unknown)},
            )

    await enqueue_events(batch.events)
    await flush_events()

    # Fire detection AFTER commit
    asyncio.create_task(run_detection(batch.events))

    return {"accepted": len(batch.events)}


@router.post("/events/mcp")
async def ingest_mcp_events(
    batch: EventBatch,
    auth_user_id: str = Depends(get_auth_user_id),
) -> dict:
    """Ingest events from tracea-mcp (Claude Code / OpenClaw integration).

    Marks all events with integration=tracea-mcp metadata.
    """
    if len(batch.events) > _MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=413,
            detail={"error": "batch_too_large", "max": _MAX_BATCH_SIZE, "received": len(batch.events)}
        )

    # Inject user_id from authenticated API key if event lacks one
    for event in batch.events:
        if not event.user_id and auth_user_id:
            event.user_id = auth_user_id

    # Validate non-empty user_ids against users table
    unique_user_ids = {e.user_id for e in batch.events if e.user_id}
    if unique_user_ids:
        db = await anext(get_db())
        placeholders = ",".join("?" for _ in unique_user_ids)
        rows = await db.execute(
            f"SELECT user_id FROM users WHERE user_id IN ({placeholders})",
            tuple(unique_user_ids),
        )
        found = {r["user_id"] for r in await rows.fetchall()}
        unknown = unique_user_ids - found
        if unknown:
            raise HTTPException(
                status_code=400,
                detail={"error": "unknown_user_ids", "unknown": sorted(unknown)},
            )

    for event in batch.events:
        if event.metadata is None:
            event.metadata = {}
        event.metadata["integration"] = "tracea-mcp"

    await enqueue_events(batch.events)
    await flush_events()
    asyncio.create_task(run_detection(batch.events))

    return {"accepted": len(batch.events)}