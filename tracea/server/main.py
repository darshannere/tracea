import os
import asyncio
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from tracea.server.db import init_db, close_db, get_db
from tracea.server.detection.watcher import start_watching, stop_watching
from tracea.server.alerts.watcher import start_watching as start_alerts_watching, stop_watching as stop_alerts_watching
from tracea.server.alerts.dispatcher import start_dispatcher, stop_dispatcher
from tracea.server.rca.worker import start_worker, stop_worker

start_time = time.time()
_retention_task: asyncio.Task | None = None
_watcher_task: asyncio.Task | None = None
_dispatcher_task: asyncio.Task | None = None
_rca_worker_task: asyncio.Task | None = None


async def retention_cleanup():
    """Delete sessions older than TRACEA_RETENTION_DAYS every hour."""
    retention_days = int(os.getenv("TRACEA_RETENTION_DAYS", "30"))
    cutoff = f"datetime('now', '-{retention_days} days')"
    while True:
        await asyncio.sleep(3600)
        try:
            db = await anext(get_db())
            old = await db.execute(f"SELECT session_id FROM sessions WHERE started_at < {cutoff}")
            for (sid,) in [row async for row in old]:
                await db.execute("DELETE FROM alerts WHERE issue_id IN (SELECT issue_id FROM issues WHERE session_id = ?)", (sid,))
                await db.execute("DELETE FROM issues WHERE session_id = ?", (sid,))
                await db.execute("DELETE FROM events WHERE session_id = ?", (sid,))
                await db.execute("DELETE FROM sessions WHERE session_id = ?", (sid,))
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
    await start_worker()          # RCAWorker
    yield
    if _retention_task:
        _retention_task.cancel()
    await stop_watching()
    await stop_alerts_watching()   # alerts.yaml watcher
    await stop_dispatcher()        # AlertDispatcher
    await stop_worker()           # RCAWorker
    await close_db()


app = FastAPI(title="tracea", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "db": "ok", "uptime_s": int(time.time() - start_time)}


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

app.include_router(ingest_router)
app.include_router(sessions_router)
app.include_router(issues_router)
app.include_router(config_router)
app.include_router(agents_router)


def create_app() -> FastAPI:
    return app
