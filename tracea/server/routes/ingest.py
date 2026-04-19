from fastapi import APIRouter, Depends
from tracea.server.models import EventBatch
from tracea.server.auth import bearer_auth
from tracea.server.db import enqueue_events

router = APIRouter(prefix="/api/v1", tags=["ingest"])


@router.post("/events")
async def ingest_events(
    batch: EventBatch,
    _api_key: str = Depends(bearer_auth)
) -> dict:
    await enqueue_events(batch.events)
    return {"accepted": len(batch.events)}
