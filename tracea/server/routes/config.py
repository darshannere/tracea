"""Config API — YAML config read/write for Settings page."""
import os
import tempfile
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/config", tags=["config"])


class ConfigContent(BaseModel):
    content: str


def _read_yaml(path: str) -> str:
    full = os.getenv("TRACEA_DATA_DIR", "./data")
    file_path = os.path.join(full, path)
    if os.path.exists(file_path):
        with open(file_path) as f:
            return f.read()
    # Fall back to defaults (same fallback as RulesLoader)
    # Try Docker path first, then local dev path
    for default_dir in ["/app/defaults", "tracea/server/detection/defaults"]:
        default_path = os.path.join(default_dir, path)
        if os.path.exists(default_path):
            with open(default_path) as f:
                return f.read()
    return ""


def _write_yaml(path: str, content: str) -> None:
    full = os.getenv("TRACEA_DATA_DIR", "./data")
    file_path = os.path.join(full, path)
    # Atomic write: temp file + rename
    fd, tmp = tempfile.mkstemp(dir=full, suffix=".yaml")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.rename(tmp, file_path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


@router.get("/rules")
async def get_rules():
    """Return raw YAML content of detection_rules.yaml."""
    content = _read_yaml("detection_rules.yaml")
    return {"content": content}


@router.put("/rules")
async def put_rules(body: ConfigContent):
    """Write new detection_rules.yaml content and trigger hot-reload."""
    # Validate YAML first
    try:
        from ruamel.yaml import YAML
        YAML().load(body.content)
    except Exception as e:
        raise HTTPException(status_code=422, detail={"error": "YAML parse error", "detail": str(e)})

    # Write atomically
    _write_yaml("detection_rules.yaml", body.content)

    # Trigger hot-reload
    try:
        from tracea.server.detection.watcher import reload_rules
        await reload_rules()
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": f"Reload failed: {e}"})

    return {"status": "ok", "message": "Rules reloaded"}


@router.get("/alerts")
async def get_alerts():
    """Return raw YAML content of alerts.yaml."""
    content = _read_yaml("alerts.yaml")
    return {"content": content}


@router.put("/alerts")
async def put_alerts(body: ConfigContent):
    """Write new alerts.yaml content and trigger hot-reload."""
    # Validate YAML first
    try:
        from ruamel.yaml import YAML
        YAML().load(body.content)
    except Exception as e:
        raise HTTPException(status_code=422, detail={"error": "YAML parse error", "detail": str(e)})

    # Write atomically
    _write_yaml("alerts.yaml", body.content)

    # Trigger hot-reload
    try:
        from tracea.server.alerts.watcher import reload_alerts
        await reload_alerts()
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": f"Reload failed: {e}"})

    return {"status": "ok", "message": "Alerts config reloaded"}


@router.get("/rca")
async def get_rca():
    """Return current RCA backend configuration."""
    return {
        "backend": os.getenv("TRACEA_RCA_BACKEND", "disabled"),
        "model": os.getenv("TRACEA_RCA_MODEL", ""),
    }
