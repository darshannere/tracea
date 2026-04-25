"""AlertWatcher — hot-reload alerts.yaml on filesystem changes (RulesWatcher pattern)."""

import asyncio
import os
from watchfiles import awatch
from tracea.server.alerts.models import AlertsConfig, load_alerts_config

_alerts_config: AlertsConfig | None = None
_config_lock = asyncio.Lock()
_stop_watching: asyncio.Event | None = None


async def reload_alerts(path: str | None = None) -> None:
    """Reload alerts config atomically."""
    global _alerts_config
    alert_path = path or os.getenv("TRACEA_ALERTS_PATH", "./data/alerts.yaml")
    try:
        config = load_alerts_config(alert_path)
        async with _config_lock:
            _alerts_config = config
        print(f"[tracea] Reloaded alerts config from {alert_path}")
    except Exception as e:
        print(f"[tracea] Alerts reload failed: {e}. Retaining last valid config.")


async def get_alerts_config() -> AlertsConfig | None:
    async with _config_lock:
        return _alerts_config


async def _watch_loop(path: str | None = None) -> None:
    global _stop_watching
    alert_path = path or os.getenv("TRACEA_ALERTS_PATH", "./data/alerts.yaml")
    try:
        await reload_alerts(alert_path)
        async for changes in awatch(alert_path):
            await reload_alerts(alert_path)
            if _stop_watching and _stop_watching.is_set():
                break
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[tracea] AlertWatcher error: {e}")


async def start_watching(path: str | None = None) -> None:
    global _stop_watching
    _stop_watching = asyncio.Event()
    asyncio.create_task(_watch_loop(path))


async def stop_watching() -> None:
    global _stop_watching
    if _stop_watching:
        _stop_watching.set()