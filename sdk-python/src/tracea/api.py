"""Async HTTP client for posting events to the tracea server."""
from __future__ import annotations
import httpx
from tracea.config import get_config
from tracea.events import TracedEvent, EventBatch

class TraceaAPIClient:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            config = get_config()
            headers = {}
            if config.api_key:
                headers["Authorization"] = f"Bearer {config.api_key}"
            self._client = httpx.AsyncClient(
                base_url=config.base_url,
                headers=headers,
                timeout=10.0,
            )
        return self._client

    async def post_events(self, events: list[TracedEvent]) -> int:
        """POST event batch to server. Returns accepted count. Raises on error."""
        client = await self._get_client()
        batch = EventBatch(events=events)
        response = await client.post("/api/v1/events", json=batch.to_dict())
        response.raise_for_status()
        data = response.json()
        return data.get("accepted", len(events))

    async def close(self) -> None:
        """Close the underlying client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None