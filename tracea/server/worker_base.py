"""worker_base.py — Generic background polling worker base."""
import asyncio
from typing import Callable, Awaitable, Any
import logging
from tracea.server.rca.backends import load_backend, RCABackend
from tracea.server.rca.models import RCABackendConfig
from tracea.server.rca.prompts import load_custom_prompt

logger = logging.getLogger("tracea")


class PollingWorker:
    """Generic background task runner that polls a database for work."""

    def __init__(
        self,
        name: str,
        config_loader: Callable[[], Awaitable[RCABackendConfig]],
        fetch_pending: Callable[[Any], Awaitable[list[Any]]],
        process_item: Callable[[RCABackend, RCABackendConfig, str | None, Any], Awaitable[None]],
        open_db: Callable[[], Awaitable[Any]],
        poll_interval: float = 5.0,
    ):
        self.name = name
        self.config_loader = config_loader
        self.fetch_pending = fetch_pending
        self.process_item = process_item
        self.open_db = open_db
        self.poll_interval = poll_interval
        self.task: asyncio.Task | None = None
        self.stop_event: asyncio.Event | None = None

    async def start(self) -> None:
        """Start the background task loop."""
        self.stop_event = asyncio.Event()
        self.task = asyncio.create_task(self._loop())
        logger.info(f"[{self.name}] worker started")

    async def stop(self) -> None:
        """Signal the worker to stop and wait for it to cancel."""
        if self.stop_event:
            self.stop_event.set()
        if self.task:
            self.task.cancel()
        logger.info(f"[{self.name}] worker stopped")

    async def _loop(self) -> None:
        """The main polling loop."""
        while True:
            if self.stop_event and self.stop_event.is_set():
                break
            await asyncio.sleep(self.poll_interval)

            try:
                # Reload config each poll
                config = await self.config_loader()
                if config.backend == "disabled":
                    continue

                try:
                    backend = load_backend(config)
                except Exception as e:
                    logger.error(f"[{self.name}] Backend load failed: {e}")
                    continue

                custom_prompt = load_custom_prompt(config.prompt_path)

                # Open DB to fetch pending items
                db = await self.open_db()
                try:
                    items = await self.fetch_pending(db)
                finally:
                    await db.close()

                for item in items:
                    try:
                        await self.process_item(backend, config, custom_prompt, item)
                    except Exception as e:
                        logger.error(f"[{self.name}] Unexpected error processing item: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[{self.name}] Polling worker error: {e}")
