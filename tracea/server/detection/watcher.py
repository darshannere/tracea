"""RulesWatcher — hot-reload detection rules from YAML on filesystem changes."""
import asyncio
import os
from watchfiles import awatch
from tracea.server.detection.loader import RulesLoader

_rules: list[dict] = []
_rules_lock = asyncio.Lock()
_loader = RulesLoader()


async def reload_rules(path: str | None = None) -> None:
    """Reload rules atomically. Fail-closed: retain last valid set on any error."""
    global _rules
    try:
        if path:
            _loader.path = path
        rules = _loader.load()
        async with _rules_lock:
            _rules = rules
        print(f"[tracea] Reloaded {len(rules)} rules from {path or _loader.path}")
    except Exception as e:
        print(f"[tracea] Rule reload failed: {e}. Retaining last valid rule set.")


async def get_rules() -> list[dict]:
    """Return a copy of the current rule set (thread-safe)."""
    async with _rules_lock:
        return list(_rules)


async def _watch_loop(path: str | None = None) -> None:
    """Internal watch loop. Exits when _stop_watching is set."""
    global _stop_watching
    rule_path = path or os.getenv("TRACEA_RULES_PATH", "./data/detection_rules.yaml")
    try:
        await reload_rules(rule_path)
        async for changes in awatch(rule_path):
            await reload_rules(rule_path)
            if _stop_watching and _stop_watching.is_set():
                break
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[tracea] Watch loop error: {e}")


_stop_watching: asyncio.Event | None = None


async def start_watching(path: str | None = None) -> None:
    """Start watching rules. Creates background task."""
    global _stop_watching
    _stop_watching = asyncio.Event()
    asyncio.create_task(_watch_loop(path))


async def stop_watching() -> None:
    """Stop the watcher."""
    global _stop_watching
    if _stop_watching:
        _stop_watching.set()