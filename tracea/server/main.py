import os
import asyncio
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from tracea.server.db import init_db, close_db, get_db
from tracea.server.detection.watcher import start_watching, stop_watching
from tracea.server.alerts import (
    start_watching as start_alerts_watching,
    stop_watching as stop_alerts_watching,
    start_dispatcher,
    stop_dispatcher,
)
from tracea.server.rca.worker import start_worker as start_rca_worker, stop_worker as stop_rca_worker
from tracea.server.brain.synthesizer import start_worker as start_brain_worker, stop_worker as stop_brain_worker

start_time = time.time()
_retention_task: asyncio.Task | None = None
_watcher_task: asyncio.Task | None = None
_dispatcher_task: asyncio.Task | None = None
_rca_worker_task: asyncio.Task | None = None


async def retention_cleanup():
    """Delete sessions older than TRACEA_RETENTION_DAYS every hour."""
    while True:
        await asyncio.sleep(3600)
        try:
            retention_days = int(os.getenv("TRACEA_RETENTION_DAYS", "30"))
            db = get_db()
            await db.execute(
                "DELETE FROM sessions WHERE datetime(started_at) < datetime('now', ?)",
                (f"-{retention_days} days",)
            )
            await db.commit()
        except Exception as e:
            print(f"[tracea] Retention failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _retention_task, _watcher_task, _dispatcher_task, _rca_worker_task
    await init_db()
    _retention_task = asyncio.create_task(retention_cleanup())
    await start_watching()
    await start_alerts_watching()   # alerts.yaml watcher
    await start_dispatcher()       # AlertDispatcher
    await start_rca_worker()      # RCAWorker
    await start_brain_worker()    # Brain Synthesizer
    yield
    if _retention_task:
        _retention_task.cancel()
    await stop_watching()
    await stop_alerts_watching()   # alerts.yaml watcher
    await stop_dispatcher()        # AlertDispatcher
    await stop_rca_worker()       # RCAWorker
    await stop_brain_worker()     # Brain Synthesizer
    await close_db()


app = FastAPI(title="tracea", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    db_ok = "ok"
    try:
        db = get_db()
        await db.execute("SELECT 1")
    except Exception as e:
        db_ok = f"error: {e}"
    return {"status": "ok", "db": db_ok, "uptime_s": int(time.time() - start_time)}


@app.get("/")
async def root():
    return JSONResponse({
        "name": "tracea",
        "version": "0.1.0",
        "docs": "See README.md for API reference and dashboard setup"
    })

from tracea.server.routes.ingest import router as ingest_router
from tracea.server.routes.sessions import router as sessions_router
from tracea.server.routes.issues import router as issues_router
from tracea.server.routes.config import router as config_router
from tracea.server.routes.agents import router as agents_router
from tracea.server.routes.live_views import router as live_views_router
from tracea.server.routes.brain import router as brain_router
from tracea.server.routes.otlp import router as otlp_router

app.include_router(ingest_router)
app.include_router(sessions_router)
app.include_router(issues_router)
app.include_router(config_router)
app.include_router(agents_router)
app.include_router(live_views_router)
app.include_router(brain_router)
app.include_router(otlp_router)

