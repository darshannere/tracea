import os
import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

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
    """Delete sessions older than TRACEA_RETENTION_DAYS every hour.

    Deleting from ``sessions`` cascades to events, issues, alerts,
    webhook_failures, spans, metrics, and brain_entries via the triggers
    added in migrations 015 + 018 — no manual per-table deletes needed.
    """
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


async def _bootstrap_admin_if_needed() -> None:
    """On first run in api_key mode, create an admin user + API key and log it.

    Only triggers when TRACEA_AUTH_MODE=api_key AND the users table is empty.
    The plaintext key is printed exactly once so an operator can grab it from
    the container logs. The stored hash cannot be reversed.
    """
    if os.getenv("TRACEA_AUTH_MODE", "disabled") != "api_key":
        return
    import secrets
    import hashlib
    try:
        db = get_db()
        row = await (await db.execute("SELECT COUNT(*) AS n FROM users")).fetchone()
        if int(row["n"]) > 0:
            return  # already bootstrapped
        admin_id = os.getenv("TRACEA_BOOTSTRAP_USER_ID", "admin")
        await db.execute(
            "INSERT INTO users (user_id, name, email) VALUES (?, ?, ?)",
            (admin_id, "Admin", ""),
        )
        plaintext = "tr_" + secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
        await db.execute(
            "INSERT INTO api_keys (key_hash, user_id, name) VALUES (?, ?, ?)",
            (key_hash, admin_id, "bootstrap"),
        )
        await db.commit()
        print("=" * 72)
        print("[tracea] Bootstrapped initial admin user and API key:")
        print(f"[tracea]   user_id: {admin_id}")
        print(f"[tracea]   API key: {plaintext}")
        print("[tracea]   (This is printed ONCE. Store it now; it cannot be recovered.)")
        print("=" * 72)
    except Exception as e:
        print(f"[tracea] Bootstrap failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _retention_task
    started_components: list[tuple[str, ...]] = []
    try:
        await init_db()
        await _bootstrap_admin_if_needed()
        _retention_task = asyncio.create_task(retention_cleanup())
        await start_watching()
        started_components.append(("detection watcher",))
        await start_alerts_watching()
        started_components.append(("alerts watcher",))
        await start_dispatcher()
        started_components.append(("dispatcher",))
        await start_rca_worker()
        started_components.append(("rca worker",))
        await start_brain_worker()
        started_components.append(("brain worker",))
        yield
    except Exception as e:
        print(f"[tracea] Startup error: {e}")
        raise
    finally:
        if _retention_task:
            _retention_task.cancel()
        # stop_* helpers are tolerant of never-started components.
        await stop_watching()
        await stop_alerts_watching()
        await stop_dispatcher()
        await stop_rca_worker()
        await stop_brain_worker()
        await close_db()


app = FastAPI(title="tracea", version="0.1.0", lifespan=lifespan)

# CORS — allow the dashboard (dev :5173, or any deployed origin) to call the API.
# In dev, Vite's proxy already hides this, but production deployments serve the
# dashboard from a different origin and need explicit CORS headers.
_origins = [o.strip() for o in os.getenv("TRACEA_CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


# Serve the built dashboard from dist/ if present (single-origin production deploy).
# The dashboard is built via `cd dashboard && npm run build` and the dist/
# directory is mounted/copied alongside the server. This lets a single server
# process serve both API and dashboard without a separate static host or CORS.
_DASHBOARD_DIST = Path(os.getenv("TRACEA_DASHBOARD_DIST", "dashboard/dist"))
if _DASHBOARD_DIST.is_dir():
    assets_dir = _DASHBOARD_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="dashboard-assets")

    @app.get("/dashboard/{full_path:path}")
    async def _dashboard_spa(full_path: str):
        target = _DASHBOARD_DIST / full_path
        if target.is_file():
            return FileResponse(str(target))
        # SPA fallback to index.html for client-side routing
        index = _DASHBOARD_DIST / "index.html"
        if index.is_file():
            return FileResponse(str(index))
        return JSONResponse({"error": "dashboard not built"}, status_code=404)
