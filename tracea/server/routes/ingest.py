from fastapi import APIRouter, HTTPException, Depends
from tracea.server.models import EventBatch
from tracea.server.db import enqueue_events, flush_events, get_db
from tracea.server.auth import get_auth_user_id
import asyncio
from tracea.server.detection.engine import run_detection

router = APIRouter(prefix="/api/v1", tags=["ingest"])

_MAX_BATCH_SIZE = 1000


async def _validate_user_ids(events) -> None:
    """Reject events whose user_id is not present in the users table.

    Called by both HTTP ingest endpoints and (via the OTLP mapper) the OTLP
    logs path, so OTLP-sourced events cannot pollute multi-tenant filtering
    with arbitrary user_ids.
    """
    unique_user_ids = {e.user_id for e in events if e.user_id}
    if not unique_user_ids:
        return
    db = get_db()
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


async def _ingest(events, auth_user_id: str, mark_integration: str | None = None) -> int:
    """Shared ingest path: inject auth user_id, validate, enqueue, detect.

    Returns the number of accepted events. Fires detection as a tracked
    background task so the GC cannot cancel it.
    """
    if len(events) > _MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=413,
            detail={"error": "batch_too_large", "max": _MAX_BATCH_SIZE, "received": len(events)}
        )

    # Inject user_id from authenticated API key if event lacks one
    for event in events:
        if not event.user_id and auth_user_id:
            event.user_id = auth_user_id
        if mark_integration:
            if event.metadata is None:
                event.metadata = {}
            event.metadata.setdefault("integration", mark_integration)

    await _validate_user_ids(events)

    await enqueue_events(events)
    await flush_events()

    # Fire detection AFTER commit (tracked so it is not GC'd mid-run)
    from tracea.server.detection.watcher import track_task
    track_task(asyncio.create_task(run_detection(events)))

    return len(events)


@router.post("/events")
async def ingest_events(
    batch: EventBatch,
    auth_user_id: str = Depends(get_auth_user_id),
) -> dict:
    accepted = await _ingest(batch.events, auth_user_id)
    return {"accepted": accepted}


@router.post("/events/mcp")
async def ingest_mcp_events(
    batch: EventBatch,
    auth_user_id: str = Depends(get_auth_user_id),
) -> dict:
    """Ingest events from tracea-mcp (Claude Code / OpenClaw integration).

    Marks all events with integration=tracea-mcp metadata.
    """
    accepted = await _ingest(batch.events, auth_user_id, mark_integration="tracea-mcp")
    return {"accepted": accepted}
