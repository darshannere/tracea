from fastapi import APIRouter, Depends
from tracea.server.models import EventBatch
from tracea.server.auth import bearer_auth
from tracea.server.db import enqueue_events
import asyncio
from tracea.server.detection.engine import run_detection

router = APIRouter(prefix="/api/v1", tags=["ingest"])


@router.post("/events")
async def ingest_events(
    batch: EventBatch,
    _api_key: str = Depends(bearer_auth)
) -> dict:
    await enqueue_events(batch.events)

    # Fire detection AFTER enqueue (SQLite commit is async via buffer flush)
    asyncio.create_task(run_detection(batch.events))

    return {"accepted": len(batch.events)}