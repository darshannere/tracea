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
    """Internal watch loop. Exits when _stop_watching is set.

    Reconnects with exponential backoff on transient FS errors so a one-off
    inotify/permission hiccup does not permanently kill hot-reload.
    """
    global _stop_watching
    rule_path = path or os.getenv("TRACEA_RULES_PATH", "./data/detection_rules.yaml")
    backoff = 1.0
    while True:
        if _stop_watching and _stop_watching.is_set():
            return
        try:
            await reload_rules(rule_path)
            async for changes in awatch(rule_path):
                await reload_rules(rule_path)
                if _stop_watching and _stop_watching.is_set():
                    return
            # awatch exited without error — re-arm and continue.
            backoff = 1.0
        except asyncio.CancelledError:
            return
        except Exception as e:
            print(f"[tracea] Watch loop error: {e}. Reconnecting in {int(backoff)}s...")
            try:
                await asyncio.wait_for(_stop_watching.wait(), timeout=backoff)  # type: ignore[arg-type]
                return  # stop signaled during sleep
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, 30.0)


_stop_watching: asyncio.Event | None = None
_watcher_task: asyncio.Task | None = None
# Keep strong references to short-lived fire-and-forget tasks so the GC does
# not cancel them mid-execution (Python's asyncio docs warn about this).
_bg_tasks: set[asyncio.Task] = set()


async def start_watching(path: str | None = None) -> None:
    """Start watching rules. Creates background task with a strong reference."""
    global _stop_watching, _watcher_task
    _stop_watching = asyncio.Event()
    _watcher_task = asyncio.create_task(_watch_loop(path))


async def stop_watching() -> None:
    """Stop the watcher."""
    global _stop_watching, _watcher_task
    if _stop_watching:
        _stop_watching.set()
    if _watcher_task:
        _watcher_task.cancel()


def track_task(task: asyncio.Task) -> None:
    """Register a fire-and-forget task so it is not garbage-collected."""
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)